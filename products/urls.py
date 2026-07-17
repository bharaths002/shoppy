from django.urls import path
from .views import (
    ProductListView, ProductDetailView,
    ProductImageUploadView, ProductVariantView,
    FeaturedProductsView, NewArrivalsView,
)

urlpatterns = [
    path('', ProductListView.as_view(), name='product-list'),
    path('featured/', FeaturedProductsView.as_view(), name='featured-products'),
    path('new-arrivals/', NewArrivalsView.as_view(), name='new-arrivals'),
    path('<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
    path('<slug:slug>/images/', ProductImageUploadView.as_view(), name='product-images'),
    path('<slug:slug>/images/<int:image_id>/', ProductImageUploadView.as_view(), name='product-image-delete'),
    path('<slug:slug>/variants/', ProductVariantView.as_view(), name='product-variants'),
    path('<slug:slug>/variants/<str:sku>/', ProductVariantView.as_view(), name='product-variant-detail'),
]