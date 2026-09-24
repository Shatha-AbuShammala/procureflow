from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        MANAGER = "MANAGER", "Manager"
        PROCUREMENT_OFFICER = "PROCUREMENT_OFFICER", "Procurement Officer"
        ADMIN = "ADMIN", "Admin"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )