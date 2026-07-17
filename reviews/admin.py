from django.contrib import admin
from .models import Review, ReviewHelpful


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'product', 'rating',
        'is_verified_purchase', 'is_active', 'created_at'
    ]
    list_filter = ['rating', 'is_verified_purchase', 'is_active']
    search_fields = ['user__email', 'product__name', 'body']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ReviewHelpful)
class ReviewHelpfulAdmin(admin.ModelAdmin):
    list_display = ['user', 'review', 'created_at']
    search_fields = ['user__email']