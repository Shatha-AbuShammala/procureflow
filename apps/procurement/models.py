from decimal import Decimal

from django.conf import settings
from django.db import models


class PurchaseRequest(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )

    title = models.CharField(max_length=255)

    description = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def total_estimated_cost(self):
        return sum(
            (
                item.quantity * item.estimated_unit_price
                for item in self.items.all()
            ),
            Decimal("0.00"),
        )

    def __str__(self):
        return f"PR-{self.id} - {self.title}"


class PurchaseRequestItem(models.Model):

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )

    item_name = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
    )

    quantity = models.PositiveIntegerField()

    estimated_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"


class Approval(models.Model):

    class Status(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    purchase_request = models.OneToOneField(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="approval",
    )

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_request_approvals",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
    )

    comment = models.TextField(
        blank=True,
    )

    decided_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"{self.purchase_request} "
            f"{self.status} by {self.approver}"
        )