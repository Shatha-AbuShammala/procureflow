from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
import uuid
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
            (item.quantity * item.estimated_unit_price for item in self.items.all()),
            Decimal("0.00"),
        )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED"]
                ),
                name="pr_valid_status",
            )
        ]

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

    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    estimated_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="pr_item_positive_quantity"
            ),
            models.CheckConstraint(
                condition=models.Q(estimated_unit_price__gte=0),
                name="pr_item_nonnegative_price",
            ),
        ]

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

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["APPROVED", "REJECTED"]),
                name="approval_valid_status",
            )
        ]

    def __str__(self):
        return f"{self.purchase_request} " f"{self.status} by {self.approver}"


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

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "SENT", "CLOSED"]),
                name="rfq_valid_status",
            )
        ]

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
        validators=[MinValueValidator(Decimal("0.01"))],
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
            ),
            models.UniqueConstraint(
                fields=["rfq"],
                condition=models.Q(status="SELECTED"),
                name="one_selected_quote_per_rfq",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gt=0), name="quote_positive_total"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["SUBMITTED", "SELECTED", "REJECTED"]),
                name="quote_valid_status",
            ),
        ]

    def __str__(self):
        return f"Quote-{self.id} from {self.supplier}"


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially Received"
        COMPLETED = "COMPLETED", "Completed"

    purchase_request = models.OneToOneField(
        "procurement.PurchaseRequest",
        on_delete=models.PROTECT,
        related_name="purchase_order",
    )
    selected_quote = models.OneToOneField(
        "procurement.SupplierQuote",
        on_delete=models.PROTECT,
        related_name="purchase_order",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_purchase_orders",
    )
    order_number = models.CharField(
        max_length=50,
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    expected_delivery_date = models.DateField()
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gt=0), name="po_positive_total"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["OPEN", "PARTIALLY_RECEIVED", "COMPLETED"]
                ),
                name="po_valid_status",
            ),
        ]

    def __str__(self):
        return str(self.order_number)


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="items",
    )
    item_name = models.CharField(max_length=255)
    ordered_quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ordered_quantity__gte=1),
                name="po_item_positive_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0), name="po_item_positive_price"
            ),
        ]

    @property
    def line_total(self):
        return self.ordered_quantity * self.unit_price


class Receiving(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="receivings",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    received_at = models.DateTimeField(auto_now_add=True)


class ReceivingItem(models.Model):
    receiving = models.ForeignKey(
        Receiving,
        on_delete=models.PROTECT,
        related_name="items",
    )
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem,
        on_delete=models.PROTECT,
        related_name="receiving_items",
    )
    received_quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["receiving", "purchase_order_item"],
                name="unique_item_per_receiving",
            ),
            models.CheckConstraint(
                condition=models.Q(received_quantity__gte=1),
                name="receiving_positive_quantity",
            ),
        ]
