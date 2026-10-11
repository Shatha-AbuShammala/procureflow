from decimal import Decimal
from django.db import transaction
from rest_framework import serializers

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

        return items

    @transaction.atomic
    def create(self, validated_data):

        items_data = validated_data.pop("items")

        purchase_request = PurchaseRequest.objects.create(
            **validated_data
        )

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

            if rfq.status != RFQ.Status.SENT:
                raise serializers.ValidationError(
                    "Quotes can only be submitted for sent RFQs."
                )

            if not rfq.suppliers.filter(
                pk=supplier.pk
            ).exists():
                raise serializers.ValidationError(
                    "This supplier is not invited to this RFQ."
                )

            if supplier.company_id != rfq.purchase_request.company_id:
                raise serializers.ValidationError(
                    "Supplier must belong to the same company."
                )

        return attrs


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

        purchase_request = attrs.get(
            "purchase_request"
        )

        suppliers = attrs.get(
            "suppliers",
            [],
        )

        if purchase_request:

            if (
                purchase_request.company_id
                != request.user.company_id
            ):
                raise serializers.ValidationError(
                    "Invalid purchase request."
                )

            if (
                purchase_request.status
                != PurchaseRequest.Status.APPROVED
            ):
                raise serializers.ValidationError(
                    "RFQ can only be created from an approved purchase request."
                )

            if RFQ.objects.filter(
                purchase_request=purchase_request
            ).exists():
                raise serializers.ValidationError(
                    "An RFQ already exists for this purchase request."
                )

        if not suppliers:
            raise serializers.ValidationError(
                {
                    "suppliers": (
                        "At least one supplier is required."
                    )
                }
            )

        for supplier in suppliers:

            if (
                supplier.company_id
                != request.user.company_id
            ):
                raise serializers.ValidationError(
                    {
                        "suppliers": (
                            "All suppliers must belong "
                            "to your company."
                        )
                    }
                )

            if not supplier.is_active:
                raise serializers.ValidationError(
                    {
                        "suppliers": (
                            "Inactive suppliers cannot "
                            "be added to an RFQ."
                        )
                    }
                )

        return attrs    

class PurchaseOrderItemInputSerializer(serializers.Serializer):
    purchase_request_item_id = serializers.IntegerField(min_value=1)
    ordered_quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
    )


class PurchaseOrderCreateSerializer(serializers.Serializer):
    selected_quote_id = serializers.IntegerField(min_value=1)
    expected_delivery_date = serializers.DateField()
    items = PurchaseOrderItemInputSerializer(many=True)

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
    items = ReceivingItemInputSerializer(many=True)


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
    