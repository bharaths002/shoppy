from rest_framework.permissions import BasePermission


class IsAdminOrStaff(BasePermission):
    """Only admin or staff users can access this endpoint."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser)
        )