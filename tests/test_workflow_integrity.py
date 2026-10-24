from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.procurement.models import (
    Approval,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Receiving,
    ReceivingItem,
    RFQ,
    SupplierQuote,
)
from apps.procurement.services import create_purchase_order, receive_purchase_order

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("quantity,price", [(0, "1.00"), (-1, "1.00"), (1, "-0.01")])
def test_invalid_request_items_rejected(api_client, employee, quantity, price):
    api_client.force_authenticate(employee)
    response = api_client.post(
        "/api/purchase-requests/",
        {
            "title": "Invalid",
            "items": [
                {
                    "item_name": "Laptop",
                    "quantity": quantity,
                    "estimated_unit_price": price,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 400
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_amount", "0.00"),
        ("total_amount", "-1.00"),
        ("delivery_days", -1),
        ("currency", "invalid"),
    ],
)
def test_invalid_quote_values_rejected(
    api_client, workflow, supplier_a, procurement_officer, field, value
):
    workflow["quotes"][0].delete()
    api_client.force_authenticate(procurement_officer)
    data = {
        "rfq": workflow["rfq"].pk,
        "supplier": supplier_a.pk,
        "total_amount": "250.00",
        "delivery_days": 7,
    }
    data[field] = value
    assert api_client.post("/api/quotes/", data, format="json").status_code == 400


def test_expired_rfq_cannot_be_created_sent_or_quoted(
    api_client, workflow, supplier_a, procurement_officer
):
    api_client.force_authenticate(procurement_officer)
    rfq = workflow["rfq"]
    rfq.deadline = timezone.now() - timedelta(hours=1)
    rfq.status = RFQ.Status.DRAFT
    rfq.save()
    assert api_client.post(f"/api/rfqs/{rfq.pk}/send/").status_code == 400
    rfq.status = RFQ.Status.SENT
    rfq.save()
    workflow["quotes"][0].delete()
    assert (
        api_client.post(
            "/api/quotes/",
            {
                "rfq": rfq.pk,
                "supplier": supplier_a.pk,
                "total_amount": "250.00",
                "delivery_days": 7,
            },
            format="json",
        ).status_code
        == 400
    )
    rfq.delete()
    assert (
        api_client.post(
            "/api/rfqs/",
            {
                "purchase_request": workflow["pr"].pk,
                "suppliers": [supplier_a.pk],
                "deadline": (timezone.now() - timedelta(days=1)).isoformat(),
            },
            format="json",
        ).status_code
        == 400
    )


def test_inactive_supplier_cannot_quote_or_be_selected(
    api_client, workflow, supplier_a, procurement_officer
):
    api_client.force_authenticate(procurement_officer)
    supplier_a.is_active = False
    supplier_a.save()
    quote = workflow["quotes"][0]
    assert (
        api_client.post(
            f"/api/rfqs/{workflow['rfq'].pk}/quotes/{quote.pk}/select/"
        ).status_code
        == 400
    )
    quote.delete()
    assert (
        api_client.post(
            "/api/quotes/",
            {
                "rfq": workflow["rfq"].pk,
                "supplier": supplier_a.pk,
                "total_amount": "250.00",
                "delivery_days": 7,
            },
            format="json",
        ).status_code
        == 400
    )


def test_selection_records_correct_before_and_after_values(
    api_client, workflow, procurement_officer
):
    api_client.force_authenticate(procurement_officer)
    quote = workflow["quotes"][0]
    path = f"/api/rfqs/{workflow['rfq'].pk}/quotes/{quote.pk}/select/"
    assert api_client.post(path).status_code == 200
    assert api_client.post(path).status_code == 400
    log = AuditLog.objects.get(entity_type=quote._meta.label, entity_id=str(quote.pk))
    assert log.old_values == {"status": "SUBMITTED"}
    assert log.new_values == {"status": "SELECTED"}
    assert workflow["rfq"].quotes.filter(status="SELECTED").count() == 1


def test_selection_audit_failure_rolls_back_all_changes(
    api_client, workflow, procurement_officer, monkeypatch
):
    api_client.force_authenticate(procurement_officer)

    def fail(**kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("apps.procurement.views.log_action", fail)
    with pytest.raises(RuntimeError, match="audit failed"):
        api_client.post(
            f"/api/rfqs/{workflow['rfq'].pk}/quotes/{workflow['quotes'][0].pk}/select/"
        )
    workflow["rfq"].refresh_from_db()
    assert workflow["rfq"].status == RFQ.Status.SENT
    assert workflow["rfq"].quotes.filter(status="SUBMITTED").count() == 2


def test_order_accepts_items_in_any_order(
    api_client, order_payload, procurement_officer, workflow
):
    api_client.force_authenticate(procurement_officer)
    response = api_client.post("/api/purchase-orders/", order_payload, format="json")
    assert response.status_code == 201, response.data
    assert Decimal(response.data["total_amount"]) == Decimal("250.00")
    assert {item["item_name"] for item in response.data["items"]} == {
        "Laptop",
        "Monitor",
    }


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "quantity", "total", "past_date"]
)
def test_invalid_orders_leave_no_partial_records(
    api_client, order_payload, procurement_officer, change
):
    api_client.force_authenticate(procurement_officer)
    if change == "missing":
        order_payload["items"].pop()
    elif change == "duplicate":
        order_payload["items"][1] = order_payload["items"][0].copy()
    elif change == "quantity":
        order_payload["items"][0]["ordered_quantity"] = 3
    elif change == "total":
        order_payload["items"][0]["unit_price"] = "1.00"
    else:
        order_payload["expected_delivery_date"] = (
            timezone.localdate() - timedelta(days=1)
        ).isoformat()
    assert (
        api_client.post(
            "/api/purchase-orders/", order_payload, format="json"
        ).status_code
        == 400
    )
    assert PurchaseOrder.objects.count() == PurchaseOrderItem.objects.count() == 0
    assert AuditLog.objects.count() == Notification.objects.count() == 0


def test_order_audit_failure_rolls_back_items_and_callbacks(
    api_client,
    order_payload,
    procurement_officer,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    api_client.force_authenticate(procurement_officer)

    def fail(**kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("apps.procurement.services.log_action", fail)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError, match="audit failed"):
            api_client.post("/api/purchase-orders/", order_payload, format="json")
    assert callbacks == []
    assert (
        PurchaseOrder.objects.count()
        == PurchaseOrderItem.objects.count()
        == Notification.objects.count()
        == 0
    )


def test_order_notification_survives_broker_failure(
    api_client,
    order_payload,
    procurement_officer,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    api_client.force_authenticate(procurement_officer)

    def unavailable(*args, **kwargs):
        raise OSError("broker unavailable")

    monkeypatch.setattr(
        "apps.notifications.tasks.send_purchase_order_notification.delay", unavailable
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            "/api/purchase-orders/", order_payload, format="json"
        )
        assert Notification.objects.count() == 0
    assert response.status_code == 201
    assert Notification.objects.filter(recipient=procurement_officer).count() == 1


def test_service_functions_enforce_roles(employee, order_payload):
    with pytest.raises(PermissionDenied):
        create_purchase_order(
            user=employee,
            quote_id=order_payload["selected_quote_id"],
            expected_date=timezone.localdate(),
            items=[],
        )
    with pytest.raises(PermissionDenied):
        receive_purchase_order(user=employee, po_id=1, items=[])


def test_receiving_audit_failure_rolls_back_quantities(
    api_client, order_payload, procurement_officer, monkeypatch
):
    api_client.force_authenticate(procurement_officer)
    created = api_client.post("/api/purchase-orders/", order_payload, format="json")
    po = PurchaseOrder.objects.get(pk=created.data["id"])

    def fail(**kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("apps.procurement.services.log_action", fail)
    with pytest.raises(RuntimeError, match="audit failed"):
        api_client.post(
            f"/api/purchase-orders/{po.pk}/receive/",
            {
                "items": [
                    {
                        "purchase_order_item_id": po.items.first().pk,
                        "received_quantity": 1,
                    }
                ]
            },
            format="json",
        )
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.OPEN
    assert Receiving.objects.count() == ReceivingItem.objects.count() == 0


def test_receiving_rejects_foreign_items_and_empty_or_zero_quantities(
    api_client, order_payload, procurement_officer, other_procurement_officer
):
    api_client.force_authenticate(procurement_officer)
    response = api_client.post("/api/purchase-orders/", order_payload, format="json")
    path = f"/api/purchase-orders/{response.data['id']}/receive/"
    item_id = response.data["items"][0]["id"]
    for items in [
        [],
        [{"purchase_order_item_id": item_id, "received_quantity": 0}],
        [{"purchase_order_item_id": item_id + 1000, "received_quantity": 1}],
    ]:
        assert api_client.post(path, {"items": items}, format="json").status_code == 400
    api_client.force_authenticate(other_procurement_officer)
    assert (
        api_client.post(
            path,
            {"items": [{"purchase_order_item_id": item_id, "received_quantity": 1}]},
            format="json",
        ).status_code
        == 404
    )
    assert Receiving.objects.count() == 0


@pytest.mark.parametrize(
    "field,value", [("quantity", 0), ("estimated_unit_price", Decimal("-0.01"))]
)
def test_database_rejects_invalid_request_items(workflow, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        PurchaseRequestItem.objects.filter(pk=workflow["items"][0].pk).update(
            **{field: value}
        )


def test_database_allows_only_one_selected_quote(workflow):
    first, second = workflow["quotes"]
    SupplierQuote.objects.filter(pk=first.pk).update(status="SELECTED")
    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierQuote.objects.filter(pk=second.pk).update(status="SELECTED")


@pytest.mark.parametrize(
    "model,field,value",
    [
        (SupplierQuote, "total_amount", Decimal("0")),
        (SupplierQuote, "status", "UNKNOWN"),
        (PurchaseRequest, "status", "UNKNOWN"),
        (RFQ, "status", "UNKNOWN"),
    ],
)
def test_database_rejects_invalid_totals_and_statuses(workflow, model, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.all().update(**{field: value})


def race_posts(user, paths, payloads=None):
    barrier = Barrier(len(paths))

    def attempt(index):
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user)
            barrier.wait(timeout=10)
            return client.post(
                paths[index], (payloads or [{}] * len(paths))[index], format="json"
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(paths)) as executor:
        futures = [executor.submit(attempt, i) for i in range(len(paths))]
        return sorted(future.result(timeout=30) for future in futures)


@pytest.mark.django_db(transaction=True)
def test_concurrent_approval_and_rejection_have_one_decision(workflow, manager):
    pr = workflow["pr"]
    pr.status = PurchaseRequest.Status.PENDING_APPROVAL
    pr.save()
    assert race_posts(
        manager,
        [
            f"/api/purchase-requests/{pr.pk}/approve/",
            f"/api/purchase-requests/{pr.pk}/reject/",
        ],
    ) == [200, 400]
    assert Approval.objects.filter(purchase_request=pr).count() == 1
    pr.refresh_from_db()
    assert pr.status == pr.approval.status


@pytest.mark.django_db(transaction=True)
def test_concurrent_quote_selection_has_one_winner(workflow, procurement_officer):
    rfq = workflow["rfq"]
    assert race_posts(
        procurement_officer,
        [
            f"/api/rfqs/{rfq.pk}/quotes/{quote.pk}/select/"
            for quote in workflow["quotes"]
        ],
    ) == [200, 400]
    assert rfq.quotes.filter(status="SELECTED").count() == 1
    assert rfq.quotes.filter(status="REJECTED").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_order_creation_cannot_duplicate(order_payload, procurement_officer):
    assert race_posts(
        procurement_officer, ["/api/purchase-orders/"] * 2, [order_payload] * 2
    ) == [201, 400]
    assert PurchaseOrder.objects.count() == 1
    assert PurchaseOrderItem.objects.count() == 2
    assert Notification.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_quote_submission_cannot_duplicate(
    workflow, supplier_a, procurement_officer
):
    workflow["quotes"][0].delete()
    payload = {
        "rfq": workflow["rfq"].pk,
        "supplier": supplier_a.pk,
        "total_amount": "250.00",
        "delivery_days": 7,
    }
    assert race_posts(procurement_officer, ["/api/quotes/"] * 2, [payload] * 2) == [
        201,
        400,
    ]
    assert (
        SupplierQuote.objects.filter(rfq=workflow["rfq"], supplier=supplier_a).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_rfq_creation_cannot_duplicate(
    workflow, supplier_a, procurement_officer
):
    workflow["rfq"].delete()
    payload = {
        "purchase_request": workflow["pr"].pk,
        "suppliers": [supplier_a.pk],
        "deadline": (timezone.now() + timedelta(days=7)).isoformat(),
    }
    assert race_posts(procurement_officer, ["/api/rfqs/"] * 2, [payload] * 2) == [
        201,
        400,
    ]
    assert RFQ.objects.filter(purchase_request=workflow["pr"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_has_one_winner(employee):
    from rest_framework_simplejwt.tokens import RefreshToken

    token = str(RefreshToken.for_user(employee))
    assert race_posts(None, ["/api/auth/refresh/"] * 2, [{"refresh": token}] * 2) == [
        200,
        401,
    ]


@pytest.mark.django_db(transaction=True)
def test_concurrent_registration_cannot_duplicate():
    from django.contrib.auth import get_user_model

    payload = {
        "username": "concurrent_registration",
        "password": "Unique-registration-password-37!",
    }
    assert race_posts(None, ["/api/auth/register/"] * 2, [payload] * 2) == [201, 400]
    assert get_user_model().objects.filter(username=payload["username"]).count() == 1
