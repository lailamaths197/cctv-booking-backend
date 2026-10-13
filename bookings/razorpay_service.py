"""Thin wrapper around the Razorpay SDK so views stay readable and testable."""
from django.conf import settings
from django.utils import timezone

import razorpay

from .models import Payment


class RazorpayNotConfigured(Exception):
    pass


def get_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RazorpayNotConfigured(
            "Razorpay keys are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
        )
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order_for_booking(booking):
    """Create a new Razorpay order for a booking using the dynamic updated total.
    
    If the extra out-of-scope service fee changes the balance, we bypass the 
    stale cached order to ensure the client is charged the exact new amount.
    """
    # 👇 CHANGED: Retrieve dynamic total from our model property instead of a fixed field 👇
    final_amount = booking.total_payable_amount
    
    # Check if a previously created payment matching the exact current amount exists
    existing = booking.payments.filter(status=Payment.Status.CREATED, amount=final_amount).first()
    if existing:
        return existing

    client = get_client()
    # Convert the dynamic final calculated balance into paise
    amount_paise = int(final_amount * 100)
    
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"bk_{booking.pk}_{int(timezone.now().timestamp())}"[:40], # Added timestamp to prevent order-id collision
            "notes": {"booking_id": str(booking.pk)},
        }
    )
    return Payment.objects.create(
        booking=booking,
        razorpay_order_id=order["id"],
        amount=final_amount, # 👇 SAVED: Persist the accurate combined balance value
        currency=order.get("currency", "INR"),
    )


def checkout_payload(payment):
    """What the mobile app needs to open Razorpay Checkout."""
    return {
        "key_id": settings.RAZORPAY_KEY_ID,
        "order_id": payment.razorpay_order_id,
        "amount": int(payment.amount * 100),  # paise
        "currency": payment.currency,
        "booking_id": payment.booking_id,
    }


def verify_and_mark_paid(payment, razorpay_payment_id, razorpay_signature):
    """Verify the checkout signature; on success mark payment + booking paid.

    Raises razorpay.errors.SignatureVerificationError on a bad signature.
    """
    client = get_client()
    client.utility.verify_payment_signature(
        {
            "razorpay_order_id": payment.razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        }
    )
    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature = razorpay_signature
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save()

    booking = payment.booking
    booking.is_paid = True  # this flag is what unlocks "Completed" for the technician
    booking.save(update_fields=["is_paid", "updated_at"])
    return payment
