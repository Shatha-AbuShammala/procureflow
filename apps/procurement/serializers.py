from decimal import Decimal
from pathlib import Path
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from apps.suppliers.models import Supplier

from .models import (
    Approval,
    PurchaseRequest,
    PurchaseRequestItem,
    RFQ,
    SupplierQuote,
    PurchaseOrder,
    PurchaseOrderItem,
    Receiving,
    ReceivingItem,
)


class PurchaseRequestItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = PurchaseRequestItem

        fields = (
            "id",
            "item_name",
            "description",
            "quantity",
            "estimated_unit_price",
        )

        read_only_fields = ("id",)


class ApprovalSerializer(serializers.ModelSerializer):

    approver_username = serializers.CharField(
        source="approver.username",
        read_only=True,
    )

    class Meta:
        model = Approval

        fields = (
            "id",
            "approver",
            "approver_username",
            "status",
            "comment",
            "decided_at",
        )

        read_only_fields = (
            "id",
            "approver",
            "status",
            "decided_at",
        )


class ApprovalDecisionSerializer(serializers.Serializer):
    comment = serializers.CharField(
        required=False, allow_blank=True, max_length=10000, default=""
    )


class PurchaseRequestSerializer(serializers.ModelSerializer):

    items = PurchaseRequestItemSerializer(
        many=True,
    )

    requester_username = serializers.CharField(
        source="requester.username",
        read_only=True,
    )

    total_estimated_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    approval = ApprovalSerializer(
        read_only=True,
    )

    class Meta:
        model = PurchaseRequest

        fields = (
            "id",
            "title",
            "description",
            "status",
            "requester",
            "requester_username",
            "items",
            "total_estimated_cost",
            "approval",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "status",
            "requester",
            "created_at",
            "updated_at",
        )

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(
                "A purchase request must contain at least one item."
            )

        total = sum(
            (item["quantity"] * item["estimated_unit_price"] for item in items),
            Decimal("0.00"),
        )
        if total > Decimal("999999999999.99"):
            raise serializers.ValidationError(
                "Total estimated cost exceeds the supported monetary limit."
            )
        return items

    @transaction.atomic
    def create(self, validated_data):

        items_data = validated_data.pop("items")

        purchase_request = PurchaseRequest.objects.create(**validated_data)

        for item_data in items_data:
            PurchaseRequestItem.objects.create(
                purchase_request=purchase_request,
                **item_data,
            )

        return purchase_request


class SupplierQuoteSerializer(serializers.ModelSerializer):

    supplier_name = serializers.CharField(
        source="supplier.name",
        read_only=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self.context.get("request"), "user", None)
        company_id = getattr(user, "company_id", None)
        self.fields["rfq"].queryset = (
            RFQ.objects.filter(purchase_request__company_id=company_id)
            if company_id
            else RFQ.objects.none()
        )
        self.fields["supplier"].queryset = (
            Supplier.objects.filter(company_id=company_id)
            if company_id
            else Supplier.objects.none()
        )

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise serializers.ValidationError(
                "Use a three-letter currency code, for example USD."
            )
        return value

    def validate_attachment(self, value):
        if value is None:
            return value
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Attachments must be at most 5 MiB.")
        header = value.read(8)
        value.seek(0)
        suffix = Path(value.name).suffix.lower()
        valid = (
            (suffix == ".pdf" and header.startswith(b"%PDF-"))
            or (suffix == ".png" and header == b"\x89PNG\r\n\x1a\n")
            or (suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        )
        if not valid:
            raise serializers.ValidationError(
                "Upload a PDF, PNG or JPEG file with matching content."
            )
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.attachment:
            url = reverse("quote-attachment", args=[instance.pk])
            request = self.context.get("request")
            data["attachment"] = request.build_absolute_uri(url) if request else url
        return data

    class Meta:
        model = SupplierQuote

        fields = (
            "id",
            "rfq",
            "supplier",
            "supplier_name",
            "total_amount",
            "currency",
            "delivery_days",
            "payment_terms",
            "warranty",
            "attachment",
            "status",
            "submitted_at",
        )

        read_only_fields = (
            "id",
            "status",
            "submitted_at",
        )

    def validate(self, attrs):
        rfq = attrs.get("rfq")
        supplier = attrs.get("supplier")

        if rfq and supplier:

            user = getattr(self.context.get("request"), "user", None)
            if rfq.purchase_request.company_id != getattr(user, "company_id", None):
                raise serializers.ValidationError("Invalid RFQ.")

            if rfq.status != RFQ.Status.SENT:
                raise serializers.ValidationError(
                    "Quotes can only be submitted for sent RFQs."
                )

            if rfq.deadline <= timezone.now():
                raise serializers.ValidationError("The RFQ deadline has passed.")
            if not supplier.is_active:
                raise serializers.ValidationError(
                    "Inactive suppliers cannot submit quotes."
                )

            if not rfq.suppliers.filter(pk=supplier.pk).exists():
                raise serializers.ValidationError(
                    "This supplier is not invited to this RFQ."
                )

            if supplier.company_id != rfq.purchase_request.company_id:
                raise serializers.ValidationError(
                    "Supplier must belong to the same company."
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        rfq = RFQ.objects.select_for_update().get(pk=validated_data["rfq"].pk)
        validated_data["rfq"] = rfq
        self.validate(validated_data)
        if rfq.quotes.filter(supplier=validated_data["supplier"]).exists():
            raise serializers.ValidationError(
                "This supplier has already submitted a quote for this RFQ."
            )
        return super().create(validated_data)


class RFQSerializer(serializers.ModelSerializer):

    quotes = SupplierQuoteSerializer(
        many=True,
        read_only=True,
    )

    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    purchase_request_title = serializers.CharField(
        source="purchase_request.title",
        read_only=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self.context.get("request"), "user", None)
        company_id = getattr(user, "company_id", None)
        self.fields["purchase_request"].queryset = (
            PurchaseRequest.objects.filter(company_id=company_id)
            if company_id
            else PurchaseRequest.objects.none()
        )
        self.fields["suppliers"].child_relation.queryset = (
            Supplier.objects.filter(company_id=company_id)
            if company_id
            else Supplier.objects.none()
        )

    def validate_deadline(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("The deadline must be in the future.")
        return value

    class Meta:
        model = RFQ

        fields = (
            "id",
            "purchase_request",
            "purchase_request_title",
            "created_by",
            "created_by_username",
            "suppliers",
            "deadline",
            "status",
            "quotes",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_by",
            "status",
            "quotes",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context["request"]

        purchase_request = attrs.get("purchase_request")

        suppliers = attrs.get(
            "suppliers",
            [],
        )

        if purchase_request:

            if purchase_request.company_id != request.user.company_id:
                raise serializers.ValidationError("Invalid purchase request.")

            if purchase_request.status != PurchaseRequest.Status.APPROVED:
                raise serializers.ValidationError(
                    "RFQ can only be created from an approved purchase request."
                )

            if RFQ.objects.filter(purchase_request=purchase_request).exists():
                raise serializers.ValidationError(
                    "An RFQ already exists for this purchase request."
                )

        if not suppliers:
            raise serializers.ValidationError(
                {"suppliers": ("At least one supplier is required.")}
            )

        for supplier in suppliers:

            if supplier.company_id != request.user.company_id:
                raise serializers.ValidationError(
                    {"suppliers": ("All suppliers must belong " "to your company.")}
                )

            if not supplier.is_active:
                raise serializers.ValidationError(
                    {"suppliers": ("Inactive suppliers cannot " "be added to an RFQ.")}
                )

        if len({supplier.pk for supplier in suppliers}) != len(suppliers):
            raise serializers.ValidationError(
                {"suppliers": "Duplicate suppliers are not allowed."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        purchase_request = PurchaseRequest.objects.select_for_update().get(
            pk=validated_data["purchase_request"].pk
        )
        validated_data["purchase_request"] = purchase_request
        self.validate(validated_data)
        self.validate_deadline(validated_data["deadline"])
        return super().create(validated_data)


class PurchaseOrderItemInputSerializer(serializers.Serializer):
    purchase_request_item_id = serializers.IntegerField(min_value=1)
    ordered_quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class PurchaseOrderCreateSerializer(serializers.Serializer):
    selected_quote_id = serializers.IntegerField(min_value=1)
    expected_delivery_date = serializers.DateField()
    items = PurchaseOrderItemInputSerializer(many=True, allow_empty=False)

    def validate_expected_delivery_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                "Expected delivery date cannot be in the past."
            )
        return value

    def validate_items(self, value):
        ids = [item["purchase_request_item_id"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate items.")
        return value


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id",
            "item_name",
            "ordered_quantity",
            "unit_price",
            "line_total",
        ]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "order_number",
            "purchase_request",
            "selected_quote",
            "supplier",
            "total_amount",
            "expected_delivery_date",
            "status",
            "items",
            "created_at",
        ]


class ReceivingItemInputSerializer(serializers.Serializer):
    purchase_order_item_id = serializers.IntegerField(min_value=1)
    received_quantity = serializers.IntegerField(min_value=1)


class ReceivingCreateSerializer(serializers.Serializer):
    items = ReceivingItemInputSerializer(many=True, allow_empty=False)

    def validate_items(self, value):
        ids = [item["purchase_order_item_id"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Duplicate receiving items are not allowed."
            )
        return value


class ReceivingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceivingItem
        fields = [
            "purchase_order_item",
            "received_quantity",
        ]


class ReceivingSerializer(serializers.ModelSerializer):
    items = ReceivingItemSerializer(many=True, read_only=True)

    class Meta:
        model = Receiving
        fields = [
            "id",
            "purchase_order",
            "received_by",
            "received_at",
            "items",
        ]
