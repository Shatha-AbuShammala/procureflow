from rest_framework.permissions import BasePermission, SAFE_METHODS


class CanManageSuppliers(BasePermission):
    message = "You do not have permission to manage suppliers."

    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        if user.company_id is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        return user.role in (
            user.Role.PROCUREMENT_OFFICER,
            user.Role.ADMIN,
        )