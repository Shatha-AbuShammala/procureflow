from rest_framework.permissions import BasePermission


class HasCompany(BasePermission):
    message = "You must belong to a company."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.company_id is not None


class IsCompanyAdmin(BasePermission):
    message = "Only company admins can perform this action."

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and user.company_id is not None
            and user.role == user.Role.ADMIN
        )
