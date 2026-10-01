from django.db import transaction
from rest_framework import serializers

from .models import (
    Approval,
    PurchaseRequest,
    PurchaseRequestItem,
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