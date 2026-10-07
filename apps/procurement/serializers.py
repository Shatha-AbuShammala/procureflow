from django.db import transaction
from rest_framework import serializers

from .models import (
    Approval,
    PurchaseRequest,
    PurchaseRequestItem,
    RFQ,
    SupplierQuote,
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