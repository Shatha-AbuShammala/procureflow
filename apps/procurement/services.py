
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Receiving,
    ReceivingItem,
    SupplierQuote,
)


@transaction.atomic
def create_purchase_order(*, user, quote_id, expected_date, items):
    quote = (
        SupplierQuote.objects
        .select_for_update()
        .select_related("rfq__purchase_request", "supplier")
        .get(pk=quote_id)
    )

    pr = quote.rfq.purchase_request

    if pr.company_id != user.company_id:
        raise ValidationError("Quote does not belong to your company.")

    if quote.status != SupplierQuote.Status.SELECTED:
        raise ValidationError("Quote must be selected first.")

    if pr.status != pr.Status.APPROVED:
        raise ValidationError("Purchase request is not approved.")

    if PurchaseOrder.objects.filter(purchase_request=pr).exists():
        raise ValidationError("Purchase order already exists.")

    if not items:
        raise ValidationError("At least one item is required.")

    pr_items = list(pr.items.order_by("id"))
    if len(items) != len(pr_items):
        raise ValidationError("All requested items must be included.")

    total = Decimal("0.00")

    for submitted, original in zip(items, pr_items):
        if submitted["purchase_request_item_id"] != original.id:
            raise ValidationError("Items must match the purchase request.")

        if submitted["ordered_quantity"] != original.quantity:
            raise ValidationError("Ordered quantities must match the request.")

        total += (
            submitted["ordered_quantity"] *
            submitted["unit_price"]
        )

    if total != quote.total_amount:
        raise ValidationError(
            "Purchase order total must equal selected quote total."
        )

    po = PurchaseOrder.objects.create(
        purchase_request=pr,
        selected_quote=quote,
        supplier=quote.supplier,
        created_by=user,
        total_amount=total,
        expected_delivery_date=expected_date,
    )

    PurchaseOrderItem.objects.bulk_create([
        PurchaseOrderItem(
            purchase_order=po,
            item_name=original.item_name,
            ordered_quantity=submitted["ordered_quantity"],
            unit_price=submitted["unit_price"],
        )
        for submitted, original in zip(items, pr_items)
    ])

    return po


@transaction.atomic
def receive_purchase_order(*, user, po_id, items):
    # Lock the parent row to serialize receiving operations.
    po = (
        PurchaseOrder.objects
        .select_for_update()
        .get(pk=po_id, purchase_request__company_id=user.company_id)
    )

    if po.status == PurchaseOrder.Status.COMPLETED:
        raise ValidationError("Purchase order is already completed.")

    if not items:
        raise ValidationError("At least one receiving item is required.")

    po_items = {
        item.id: item
        for item in po.items.all()
    }

    ids = [item["purchase_order_item_id"] for item in items]

    if len(ids) != len(set(ids)):
        raise ValidationError("Duplicate items are not allowed.")

    for submitted in items:
        item_id = submitted["purchase_order_item_id"]
        quantity = submitted["received_quantity"]

        if item_id not in po_items:
            raise ValidationError("Item does not belong to this order.")

        already_received = (
            ReceivingItem.objects.filter(
                purchase_order_item_id=item_id
            ).aggregate(total=Sum("received_quantity"))["total"] or 0
        )

        if already_received + quantity > po_items[item_id].ordered_quantity:
            raise ValidationError(
                f"Receiving exceeds ordered quantity for item {item_id}."
            )

    receiving = Receiving.objects.create(
        purchase_order=po,
        received_by=user,
    )

    ReceivingItem.objects.bulk_create([
        ReceivingItem(
            receiving=receiving,
            purchase_order_item_id=item["purchase_order_item_id"],
            received_quantity=item["received_quantity"],
        )
        for item in items
    ])

    complete = True

    for po_item in po.items.all():
        received = (
            ReceivingItem.objects.filter(
                purchase_order_item=po_item
            ).aggregate(total=Sum("received_quantity"))["total"] or 0
        )

        if received < po_item.ordered_quantity:
            complete = False
            break

    po.status = (
        PurchaseOrder.Status.COMPLETED
        if complete
        else PurchaseOrder.Status.PARTIALLY_RECEIVED
    )
    po.save(update_fields=["status"])

    return receiving
