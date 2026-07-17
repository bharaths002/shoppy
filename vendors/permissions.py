from rest_framework.permissions import BasePermission


class IsVendor(BasePermission):
    """
    Allows access only to approved vendors.
    Pending or rejected vendors are blocked.
    """
    message = "You must be an approved vendor to access this."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role != 'vendor':
            return False
        try:
            return request.user.vendor_profile.status == 'approved'
        except Exception:
            return False


class IsVendorOrAdmin(BasePermission):
    """
    Approved vendors can access their own data.
    Admin can access everything.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_staff:
            return True
        if request.user.role == 'vendor':
            try:
                return request.user.vendor_profile.status == 'approved'
            except Exception:
                return False
        return False


class IsProductOwner(BasePermission):
    """
    Vendor can only modify products that belong to their own shop.
    Admin can modify any product.
    """
    message = "You can only manage your own products."

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True
        try:
            return obj.vendor == request.user.vendor_profile
        except Exception:
            return False