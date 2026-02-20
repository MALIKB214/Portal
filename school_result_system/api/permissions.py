from rest_framework.permissions import BasePermission


class IsProprietorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return getattr(user, "is_proprietor", False) or getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)
