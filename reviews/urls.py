from django.urls import path
from .views import (
    ProductReviewListView,
    ReviewDetailView,
    MarkReviewHelpfulView,
    MyReviewsView,
    AdminReviewManageView,
)

urlpatterns = [
    # Customer endpoints
    path('my-reviews/', MyReviewsView.as_view(), name='my-reviews'),
    path('<slug:product_slug>/', ProductReviewListView.as_view(), name='product-reviews'),
    path('<slug:product_slug>/<int:review_id>/', ReviewDetailView.as_view(), name='review-detail'),
    path('helpful/<int:review_id>/', MarkReviewHelpfulView.as_view(), name='review-helpful'),

    # Admin endpoints
    path('admin/all/', AdminReviewManageView.as_view(), name='admin-review-list'),
    path('admin/<int:review_id>/', AdminReviewManageView.as_view(), name='admin-review-delete'),
]