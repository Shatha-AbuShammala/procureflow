from django.contrib import admin


class PlatformAdminSite(admin.AdminSite):
    """Django admin is for platform operators, never tenant administrators."""

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser
