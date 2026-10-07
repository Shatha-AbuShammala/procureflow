from rest_framework.permissions import BasePermission


class CanManageProcurement(BasePermission):

    message = (
        "Only procurement officers and admins "
        "can perform this action."
    )

    def has_permission(self, request, view):

        user = request.user

        return (
            user.is_authenticated
            and user.company_id is not None
            and user.role
            in (
                user.Role.PROCUREMENT_OFFICER,
                user.Role.ADMIN,
            )
        )