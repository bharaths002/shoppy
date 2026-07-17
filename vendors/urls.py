from django.urls import path
from .views import (
    VendorRegisterView,
    VendorProfileView,
    VendorProductListView,
    VendorProductDetailView,
    VendorProductImageView,
    VendorVariantView,
    VendorOrderListView,
    VendorOrderDetailView,
    VendorUpdateOrderItemStatusView,
    VendorInventoryView,
    VendorUpdateProductStockView,
    VendorUpdateVariantStockView,
    VendorBulkStockUpdateView,
    VendorLowStockAlertView,
    VendorDashboardView,
)

urlpatterns = [
    # Auth
    path('register/', VendorRegisterView.as_view(), name='vendor-register'),
    path('profile/', VendorProfileView.as_view(), name='vendor-profile'),

      # Dashboard
    path('dashboard/', VendorDashboardView.as_view(), name='vendor-dashboard'),


    # Product management
    path('products/', VendorProductListView.as_view(), name='vendor-product-list'),
    path('products/<slug:slug>/', VendorProductDetailView.as_view(), name='vendor-product-detail'),
    path('products/<slug:slug>/images/', VendorProductImageView.as_view(), name='vendor-product-images'),
    path('products/<slug:slug>/images/<int:image_id>/', VendorProductImageView.as_view(), name='vendor-product-image-delete'),
    path('products/<slug:slug>/variants/', VendorVariantView.as_view(), name='vendor-variant-list'),
    path('products/<slug:slug>/variants/<str:sku>/', VendorVariantView.as_view(), name='vendor-variant-detail'),
       # Order management
    path('orders/', VendorOrderListView.as_view(), name='vendor-order-list'),
    path('orders/<uuid:order_id>/', VendorOrderDetailView.as_view(), name='vendor-order-detail'),
    path('orders/<uuid:order_id>/items/<int:item_id>/status/', VendorUpdateOrderItemStatusView.as_view(), name='vendor-item-status'),


     # Inventory management
    path('inventory/', VendorInventoryView.as_view(), name='vendor-inventory'),
    path('inventory/low-stock/', VendorLowStockAlertView.as_view(), name='vendor-low-stock'),
    path('inventory/bulk-update/', VendorBulkStockUpdateView.as_view(), name='vendor-bulk-stock'),
    path('inventory/<slug:slug>/stock/', VendorUpdateProductStockView.as_view(), name='vendor-product-stock'),
    path('inventory/<slug:slug>/variants/<str:sku>/stock/', VendorUpdateVariantStockView.as_view(), name='vendor-variant-stock'),

]


