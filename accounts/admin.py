from django.contrib import admin
from django.utils import timezone
from .models import User, Address, VendorProfile, OTP, OTPRequestLog


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'phone_number', 'role', 'is_verified', 'is_active']
    list_filter = ['role', 'is_verified', 'is_active']
    search_fields = ['email', 'phone_number', 'username']


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'city', 'state', 'address_type', 'is_default']
    list_filter = ['address_type', 'is_default', 'state']
    search_fields = ['full_name', 'phone_number', 'city']


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ['contact', 'otp', 'attempts', 'is_verified', 'created_at']
    search_fields = ['contact']


@admin.register(OTPRequestLog)
class OTPRequestLogAdmin(admin.ModelAdmin):
    list_display = ['contact', 'created_at']
    search_fields = ['contact']


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = [
        'shop_name', 'user', 'business_type',
        'status', 'commission_rate', 'is_active', 'created_at'
    ]
    list_filter = ['status', 'business_type', 'is_active']
    search_fields = ['shop_name', 'user__email', 'gstin']
    readonly_fields = ['created_at', 'updated_at', 'approved_at', 'approved_by']
    list_editable = ['commission_rate', 'is_active']

    fieldsets = (
        ('Shop Info', {
            'fields': ('user', 'shop_name', 'shop_slug', 'shop_description', 'logo', 'banner')
        }),
        ('Business Details', {
            'fields': ('business_type', 'gstin', 'pan_number', 'business_phone', 'business_email', 'business_address')
        }),
        ('Platform Settings', {
            'fields': ('status', 'rejection_reason', 'commission_rate', 'is_active')
        }),
        ('Approval Info', {
            'fields': ('approved_at', 'approved_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # ✅ Custom admin actions — approve or reject vendors in bulk
    actions = ['approve_vendors', 'reject_vendors', 'suspend_vendors']

    def approve_vendors(self, request, queryset):
        """
        Admin selects one or more pending vendors and clicks approve.
        Updates status, sets is_active=True, records who approved and when.
        """
        updated = queryset.filter(status='pending').update(
            status='approved',
            is_active=True,
            approved_at=timezone.now(),
            approved_by=request.user
        )
        # Update the user role to vendor
        for vendor in queryset:
            vendor.user.role = 'vendor'
            vendor.user.save()
        self.message_user(request, f"{updated} vendor(s) approved successfully.")
    approve_vendors.short_description = "✅ Approve selected vendors"

    def reject_vendors(self, request, queryset):
        """
        Admin selects one or more vendors and rejects them.
        """
        updated = queryset.exclude(status='rejected').update(
            status='rejected',
            is_active=False
        )
        self.message_user(request, f"{updated} vendor(s) rejected.")
    reject_vendors.short_description = "❌ Reject selected vendors"

    def suspend_vendors(self, request, queryset):
        """
        Admin suspends vendors who violate terms.
        """
        updated = queryset.filter(status='approved').update(
            status='suspended',
            is_active=False
        )
        self.message_user(request, f"{updated} vendor(s) suspended.")
    suspend_vendors.short_description = "⛔ Suspend selected vendors"