from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "ProcureFlow",
            {
                "fields": (
                    "company",
                    "role",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "ProcureFlow",
            {
                "fields": (
                    "company",
                    "role",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "company",
        "role",
        "is_staff",
    )