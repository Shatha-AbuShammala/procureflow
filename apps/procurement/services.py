from apps.audit.models import AuditLog
from apps.audit.services import log_action
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.notifications.tasks import dispatch_purchase_order_notification
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    PurchaseOrder,
    PurchaseRequest,
    PurchaseOrderItem,
    Receiving,
    ReceivingItem,
    SupplierQuote,
)


def require_procurement_user(user):
    if (
        not user.is_authenticated
        or user.company_id is None
        or user.role not in {user.Role.PROCUREMENT_OFFICER, user.Role.ADMIN}
    ):
        raise PermissionDenied(
            "Only company procurement officers and admins can perform this action."
        )


@transaction.atomic
def create_purchase_order(*, user, quote_id, expected_date, items):
    require_procurement_user(user)
    quote_ref = get_object_or_404(
        SupplierQuote.objects.select_related("rfq"),
        pk=quote_id,
        rfq__purchase_request__company_id=user.company_id,
    )
    # Use one lock for all order creation attempts against this request.
    pr = PurchaseRequest.objects.select_for_update().get(
        pk=quote_ref.rfq.purchase_request_id
    )
    quote = (
        SupplierQuote.objects.select_for_update(of=("self",))
        .select_related("rfq", "supplier")
        .get(pk=quote_id)
    )

    if pr.company_id != user.company_id:
        raise ValidationError("Quote does not belong to your company.")

    if quote.status != SupplierQuote.Status.SELECTED:
        raise ValidationError("Quote must be selected first.")
    if quote.rfq.status != quote.rfq.Status.CLOSED:
        raise ValidationError("The RFQ must be closed after quote selection.")
    if quote.supplier.company_id != user.company_id or not quote.supplier.is_active:
        raise ValidationError("The supplier must be active and belong to your company.")

    if pr.status != pr.Status.APPROVED:
        raise ValidationError("Purchase request is not approved.")

    if PurchaseOrder.objects.filter(purchase_request=pr).exists():
        raise ValidationError("Purchase order already exists.")

    if not items:
        raise ValidationError("At least one item is required.")
    if expected_date < timezone.localdate():
        raise ValidationError("Expected delivery date cannot be in the past.")

    pr_items = list(pr.items.order_by("id"))
    if len(items) != len(pr_items):
        raise ValidationError("All requested items must be included.")

    originals = {item.pk: item for item in pr_items}
    ids = [item["purchase_request_item_id"] for item in items]
    if len(ids) != len(set(ids)) or set(ids) != set(originals):
        raise ValidationError(
            "Items must match the purchase request without duplicates."
        )
    total = Decimal("0.00")

    for submitted in items:
        original = originals[submitted["purchase_request_item_id"]]

        if submitted["ordered_quantity"] != original.quantity:
            raise ValidationError("Ordered quantities must match the request.")
        if submitted["ordered_quantity"] <= 0 or submitted["unit_price"] <= 0:
            raise ValidationError("Quantities and unit prices must be positive.")

        total += submitted["ordered_quantity"] * submitted["unit_price"]

    if total != quote.total_amount:
        raise ValidationError("Purchase order total must equal selected quote total.")

    po = PurchaseOrder.objects.create(
        purchase_request=pr,
        selected_quote=quote,
        supplier=quote.supplier,
        created_by=user,
        total_amount=total,
        expected_delivery_date=expected_date,
    )

    PurchaseOrderItem.objects.bulk_create(
        [
            PurchaseOrderItem(
                purchase_order=po,
                item_name=originals[submitted["purchase_request_item_id"]].item_name,
                ordered_quantity=submitted["ordered_quantity"],
                unit_price=submitted["unit_price"],
            )
            for submitted in items
        ]
    )
    log_action(
        actor=user,
        action=AuditLog.Action.CREATE,
        entity=po,
        new_values={
            "status": str(po.status),
            "supplier_id": po.supplier_id,
            "total_amount": str(po.total_amount),
        },
    )
    transaction.on_commit(
        lambda po_id=po.id: dispatch_purchase_order_notification(po_id),
        robust=True,
    )

    return po


@transaction.atomic
def receive_purchase_order(*, user, po_id, items):
    require_procurement_user(user)
    po = get_object_or_404(
        PurchaseOrder.objects.select_for_update(of=("self",)),
        pk=po_id,
        purchase_request__company_id=user.company_id,
    )
    old_status = po.status

    if po.status == PurchaseOrder.Status.COMPLETED:
        raise ValidationError("Purchase order is already completed.")

    if not items:
        raise ValidationError("At least one receiving item is required.")

    po_items = {item.id: item for item in po.items.all()}

    ids = [item["purchase_order_item_id"] for item in items]

    if len(ids) != len(set(ids)):
        raise ValidationError("Duplicate items are not allowed.")

    for submitted in items:
        item_id = submitted["purchase_order_item_id"]
        quantity = submitted["received_quantity"]
        if quantity <= 0:
            raise ValidationError("Received quantities must be positive.")

        if item_id not in po_items:
            raise ValidationError("Item does not belong to this order.")

        already_received = (
            ReceivingItem.objects.filter(purchase_order_item_id=item_id).aggregate(
                total=Sum("received_quantity")
            )["total"]
            or 0
        )

        if already_received + quantity > po_items[item_id].ordered_quantity:
            raise ValidationError(
                f"Receiving exceeds ordered quantity for item {item_id}."
            )

    receiving = Receiving.objects.create(
        purchase_order=po,
        received_by=user,
    )

    ReceivingItem.objects.bulk_create(
        [
            ReceivingItem(
                receiving=receiving,
                purchase_order_item_id=item["purchase_order_item_id"],
                received_quantity=item["received_quantity"],
            )
            for item in items
        ]
    )

    complete = True

    for po_item in po.items.all():
        received = (
            ReceivingItem.objects.filter(purchase_order_item=po_item).aggregate(
                total=Sum("received_quantity")
            )["total"]
            or 0
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
    log_action(
        actor=user,
        action=AuditLog.Action.UPDATE,
        entity=po,
        old_values={"status": str(old_status)},
        new_values={"status": str(po.status), "receiving_id": receiving.id},
    )

    return receiving
