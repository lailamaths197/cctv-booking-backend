from django.urls import path

from .views import (
    AdminServiceDetailView,
    AdminServiceListCreateView,
    AdminStatsView,
    AssignTechnicianView,
    BookingDetailView,
    BookingListCreateView,
    CreatePaymentOrderView,
    NotificationListView,
    NotificationMarkReadView,
    PaymentHistoryView,
    ServiceCategoryListView,
    UpdateBookingStatusView,
    VerifyPaymentView,
)

urlpatterns = [
    path("services/", ServiceCategoryListView.as_view(), name="services"),
    path("bookings/", BookingListCreateView.as_view(), name="bookings"),
    path("bookings/<int:pk>/", BookingDetailView.as_view(), name="booking-detail"),
    path("bookings/<int:pk>/status/", UpdateBookingStatusView.as_view(), name="booking-status"),
    path("bookings/<int:pk>/assign/", AssignTechnicianView.as_view(), name="booking-assign"),
    path("bookings/<int:pk>/pay/", CreatePaymentOrderView.as_view(), name="booking-pay"),
    path("payments/", PaymentHistoryView.as_view(), name="payments"),
    path("payments/verify/", VerifyPaymentView.as_view(), name="payment-verify"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read/", NotificationMarkReadView.as_view(), name="notifications-read"),
    path("admin/stats/", AdminStatsView.as_view(), name="admin-stats"),
    path("admin/services/", AdminServiceListCreateView.as_view(), name="admin-services"),
    path("admin/services/<int:pk>/", AdminServiceDetailView.as_view(), name="admin-service-detail"),
]
