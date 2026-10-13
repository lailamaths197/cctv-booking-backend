from datetime import date as date_cls

from django.core.validators import RegexValidator
from rest_framework import serializers

from accounts.models import User

from .models import Address, Booking, BookingImage, Notification, Payment, ServiceCategory
from .utils import process_images

MIN_COMPLAINT_DESCRIPTION = 10


# --- Services ----------------------------------------------------------------


class ServiceCategorySerializer(serializers.ModelSerializer):
    """Read-only public view (customers only ever see active services)."""

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "description", "base_price", "service_type", "icon")


class AdminServiceSerializer(serializers.ModelSerializer):
    """Admin create / update of the service catalog."""

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "description", "base_price", "service_type", "icon", "is_active")

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Name must be at least 3 characters.")
        return value


# --- Bookings ----------------------------------------------------------------


class AddressSerializer(serializers.ModelSerializer):
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = ("id", "house_no", "street", "landmark", "city", "state", "pincode", "full_address")


class PersonSerializer(serializers.ModelSerializer):
    """Minimal public view of a customer/technician inside a booking."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "full_name", "phone_number")

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class BookingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingImage
        fields = ("id", "kind", "image", "created_at")
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    # ... keeping your relational and source field definitions unchanged ...
    service = ServiceCategorySerializer(read_only=True)
    address = AddressSerializer(read_only=True)
    customer = PersonSerializer(read_only=True)
    technician = PersonSerializer(read_only=True)
    images = BookingImageSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    time_slot_label = serializers.CharField(source="get_time_slot_display", read_only=True)
    
    # 👇 EXPLICITLY BIND THE DYNAMIC PROPERTY METHOD AS A READ-ONLY FIELD 👇
    total_payable_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "service",
            "customer",
            "technician",
            "address",
            "date",
            "time_slot",
            "time_slot_label",
            "issue_description",
            "images",
            "status",
            "status_label",
            "amount",
            "is_paid",
            "created_at",
            # 👇 ADDED TRACKING METRICS FOR DASHBOARDS 👇
            "extra_service_title",
            "extra_service_description",
            "extra_service_charge",
            "technician_incentive",
            "total_payable_amount",
        )
        read_only_fields = fields


class BookingCreateSerializer(serializers.Serializer):
    """Flat fields on purpose: nested objects are awkward in multipart/form-data.

    `images` is the SAME multipart key repeated once per file.
    """

    service = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.filter(is_active=True)
    )
    date = serializers.DateField()
    time_slot = serializers.ChoiceField(choices=Booking.TimeSlot.choices)
    issue_description = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    images = serializers.ListField(child=serializers.ImageField(), required=False)

    house_no = serializers.CharField(max_length=50)
    street = serializers.CharField(max_length=200)
    landmark = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    pincode = serializers.CharField(
        validators=[RegexValidator(r"^[1-9]\d{5}$", "Enter a valid 6-digit pincode.")]
    )

    def validate_date(self, value):
        if value < date_cls.today():
            raise serializers.ValidationError("Date cannot be in the past.")
        return value

    def validate_images(self, value):
        return process_images(value)

    def validate(self, attrs):
        description = (attrs.get("issue_description") or "").strip()
        # Description is mandatory ONLY for service complaints; optional for installations.
        if attrs["service"].service_type == ServiceCategory.ServiceType.SERVICE_COMPLAINT:
            if len(description) < MIN_COMPLAINT_DESCRIPTION:
                raise serializers.ValidationError(
                    {
                        "issue_description": (
                            f"Describe the problem (at least {MIN_COMPLAINT_DESCRIPTION} characters) "
                            "for service complaints."
                        )
                    }
                )
        attrs["issue_description"] = description
        attrs.setdefault("images", [])
        return attrs


class UpdateStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED])
    images = serializers.ListField(child=serializers.ImageField(), required=False)

    def validate_images(self, value):
        return process_images(value)

    def validate(self, attrs):
        attrs.setdefault("images", [])
        return attrs


class AssignTechnicianSerializer(serializers.Serializer):
    # If your custom User model uses lower-case string values like 'technician' directly, 
    # make sure the queryset matches your choice structure:
    technician_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role="technician", is_active=True), # Adjusted to plain string if Role proxy is absent
        source="technician",
    )


# --- Payments & notifications ------------------------------------------------


class PaymentSerializer(serializers.ModelSerializer):
    booking_id = serializers.IntegerField(read_only=True)
    service_name = serializers.CharField(source="booking.service.name", read_only=True)
    # Receipt fields
    receipt_no = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="booking.customer.get_full_name", read_only=True)
    booking_date = serializers.DateField(source="booking.date", read_only=True)
    time_slot_label = serializers.CharField(source="booking.get_time_slot_display", read_only=True)
    address = serializers.CharField(source="booking.address.full_address", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "receipt_no",
            "booking_id",
            "service_name",
            "customer_name",
            "booking_date",
            "time_slot_label",
            "address",
            "razorpay_order_id",
            "razorpay_payment_id",
            "amount",
            "currency",
            "status",
            "created_at",
            "paid_at",
        )
        read_only_fields = fields

    def get_receipt_no(self, obj):
        return f"RCPT-{obj.pk:06d}"


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "title", "message", "booking", "is_read", "created_at")
        read_only_fields = fields
