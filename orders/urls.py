from django.urls import path
from .views import (
    CreateOrderView, VerifyPaymentView,
    OrderListView, OrderDetailView, CancelOrderView,
    AdminOrderListView, AdminUpdateOrderStatusView
)

urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='create-order'),
    path('verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('', OrderListView.as_view(), name='order-list'),
    path('<uuid:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('<uuid:order_id>/cancel/', CancelOrderView.as_view(), name='cancel-order'),

    # Admin
    path('admin/all/', AdminOrderListView.as_view(), name='admin-order-list'),
    path('admin/<uuid:order_id>/status/', AdminUpdateOrderStatusView.as_view(), name='admin-update-status'),
]