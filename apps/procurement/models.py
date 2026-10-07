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

class RFQ(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        CLOSED = "CLOSED", "Closed"

    purchase_request = models.OneToOneField(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="rfq",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_rfqs",
    )

    suppliers = models.ManyToManyField(
        "suppliers.Supplier",
        related_name="rfqs",
    )

    deadline = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"RFQ-{self.id} for {self.purchase_request}"


class SupplierQuote(models.Model):

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        SELECTED = "SELECTED", "Selected"
        REJECTED = "REJECTED", "Rejected"

    rfq = models.ForeignKey(
        RFQ,
        on_delete=models.CASCADE,
        related_name="quotes",
    )

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="quotes",
    )

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=10,
        default="USD",
    )

    delivery_days = models.PositiveIntegerField()

    payment_terms = models.CharField(
        max_length=255,
        blank=True,
    )

    warranty = models.CharField(
        max_length=255,
        blank=True,
    )

    attachment = models.FileField(
        upload_to="quotes/",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rfq", "supplier"],
                name="unique_supplier_quote_per_rfq",
            )
        ]

    def __str__(self):
        return f"Quote-{self.id} from {self.supplier}"

    