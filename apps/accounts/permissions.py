from rest_framework.permissions import BasePermission


class IsCompanyAdmin(BasePermission):
    message = "Only company admins can perform this action."

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and user.company_id is not None
            and user.role == user.Role.ADMIN
        )