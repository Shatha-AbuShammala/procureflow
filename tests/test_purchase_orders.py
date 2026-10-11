
import pytest
from decimal import Decimal
from apps.procurement.models import Receiving, ReceivingItem
from rest_framework.test import APIClient
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections

from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    RFQ,
    SupplierQuote,
    PurchaseOrder,
)


@pytest.mark.django_db
def test_cannot_create_po_from_unselected_quote(
    procurement_officer,
    supplier_a,
):
    # Arrange
    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Office laptops",
        status=PurchaseRequest.Status.APPROVED,
    )

    item = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=10,
        estimated_unit_price="450.00",
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline="2026-12-01T12:00:00Z",
        status=RFQ.Status.SENT,
    )

    quote = SupplierQuote.objects.create(
        rfq=rfq,
        supplier=supplier_a,
        total_amount="5000.00",
        delivery_days=7,
        status=SupplierQuote.Status.SUBMITTED,
    )

    client = APIClient()
    client.force_authenticate(user=procurement_officer)

    # Act
    response = client.post(
        "/api/purchase-orders/",
        {
            "selected_quote_id": quote.id,
            "expected_delivery_date": "2026-12-15",
            "items": [
                {
                    "purchase_request_item_id": item.id,
                    "ordered_quantity": 10,
                    "unit_price": "500.00",
                }
            ],
        },
        format="json",
    )

    # Assert
    assert response.status_code == 400
    assert PurchaseOrder.objects.count() == 0


@pytest.mark.django_db
def test_can_create_po_from_selected_quote(
    procurement_officer,
    supplier_a,
):
    # Arrange
    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Office laptops",
        status=PurchaseRequest.Status.APPROVED,
    )

    item = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=10,
        estimated_unit_price="450.00",
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline="2026-12-01T12:00:00Z",
        status=RFQ.Status.SENT,
    )

    quote = SupplierQuote.objects.create(
        rfq=rfq,
        supplier=supplier_a,
        total_amount="5000.00",
        delivery_days=7,
        status=SupplierQuote.Status.SELECTED,
    )

    client = APIClient()
    client.force_authenticate(user=procurement_officer)

    # Act
    response = client.post(
        "/api/purchase-orders/",
        {
            "selected_quote_id": quote.id,
            "expected_delivery_date": "2026-12-15",
            "items": [
                {
                    "purchase_request_item_id": item.id,
                    "ordered_quantity": 10,
                    "unit_price": "500.00",
                }
            ],
        },
        format="json",
    )

    # Assert
    assert response.status_code == 201, response.data

    assert PurchaseOrder.objects.count() == 1

    po = PurchaseOrder.objects.get()

    assert po.purchase_request == pr
    assert po.selected_quote == quote
    assert po.supplier == supplier_a
    assert po.status == PurchaseOrder.Status.OPEN

    assert po.items.count() == 1

    po_item = po.items.first()

    assert po_item.ordered_quantity == 10
    assert po_item.unit_price == 500


@pytest.mark.django_db
def test_partial_receiving(
    procurement_officer,
    supplier_a,
):
    # Arrange: Create an approved purchase request
    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Office laptops",
        status=PurchaseRequest.Status.APPROVED,
    )

    pr_item = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=10,
        estimated_unit_price=Decimal("450.00"),
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline="2026-12-01T12:00:00Z",
        status=RFQ.Status.SENT,
    )

    quote = SupplierQuote.objects.create(
        rfq=rfq,
        supplier=supplier_a,
        total_amount=Decimal("5000.00"),
        delivery_days=7,
        status=SupplierQuote.Status.SELECTED,
    )

    client = APIClient()
    client.force_authenticate(user=procurement_officer)

    # Create Purchase Order
    po_response = client.post(
        "/api/purchase-orders/",
        {
            "selected_quote_id": quote.id,
            "expected_delivery_date": "2026-12-15",
            "items": [
                {
                    "purchase_request_item_id": pr_item.id,
                    "ordered_quantity": 10,
                    "unit_price": "500.00",
                }
            ],
        },
        format="json",
    )

    assert po_response.status_code == 201, po_response.data

    po = PurchaseOrder.objects.get()
    po_item = po.items.get()

    # Act: Receive only 6 out of 10
    response = client.post(
        f"/api/purchase-orders/{po.id}/receive/",
        {
            "items": [
                {
                    "purchase_order_item_id": po_item.id,
                    "received_quantity": 6,
                }
            ]
        },
        format="json",
    )

    # Assert
    assert response.status_code == 201, response.data

    po.refresh_from_db()

    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED

    assert Receiving.objects.filter(
        purchase_order=po
    ).count() == 1

    assert ReceivingItem.objects.filter(
        purchase_order_item=po_item
    ).first().received_quantity == 6


@pytest.fixture
def po_setup(procurement_officer, supplier_a):
    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Office laptops",
        status=PurchaseRequest.Status.APPROVED,
    )

    pr_item = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=10,
        estimated_unit_price=Decimal("450.00"),
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline="2026-12-01T12:00:00Z",
        status=RFQ.Status.SENT,
    )

    quote = SupplierQuote.objects.create(
        rfq=rfq,
        supplier=supplier_a,
        total_amount=Decimal("5000.00"),
        delivery_days=7,
        status=SupplierQuote.Status.SELECTED,
    )

    client = APIClient()
    client.force_authenticate(user=procurement_officer)

    payload = {
        "selected_quote_id": quote.id,
        "expected_delivery_date": "2026-12-15",
        "items": [{
            "purchase_request_item_id": pr_item.id,
            "ordered_quantity": 10,
            "unit_price": "500.00",
        }],
    }

    response = client.post(
        "/api/purchase-orders/",
        payload,
        format="json",
    )
    assert response.status_code == 201, response.data

    po = PurchaseOrder.objects.get(pk=response.data["id"])

    return {
        "client": client,
        "po": po,
        "po_item": po.items.get(),
        "quote": quote,
        "payload": payload,
    }


def receive(client, po, po_item, quantity):
    return client.post(
        f"/api/purchase-orders/{po.id}/receive/",
        {
            "items": [{
                "purchase_order_item_id": po_item.id,
                "received_quantity": quantity,
            }]
        },
        format="json",
    )


@pytest.mark.django_db
def test_full_receiving(po_setup):
    client = po_setup["client"]
    po = po_setup["po"]
    item = po_setup["po_item"]

    first = receive(client, po, item, 6)
    assert first.status_code == 201

    second = receive(client, po, item, 4)
    assert second.status_code == 201

    po.refresh_from_db()

    assert po.status == PurchaseOrder.Status.COMPLETED

    total = sum(
        ri.received_quantity
        for ri in ReceivingItem.objects.filter(
            purchase_order_item=item
        )
    )
    assert total == 10


@pytest.mark.django_db
def test_cannot_receive_more_than_ordered(po_setup):
    client = po_setup["client"]
    po = po_setup["po"]
    item = po_setup["po_item"]

    first = receive(client, po, item, 6)
    assert first.status_code == 201

    second = receive(client, po, item, 5)

    assert second.status_code == 400
    assert Receiving.objects.filter(
        purchase_order=po
    ).count() == 1

    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED


@pytest.mark.django_db
def test_cannot_receive_completed_po(po_setup):
    client = po_setup["client"]
    po = po_setup["po"]
    item = po_setup["po_item"]

    first = receive(client, po, item, 10)
    assert first.status_code == 201

    second = receive(client, po, item, 1)
    assert second.status_code == 400

    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.COMPLETED


@pytest.mark.django_db
def test_cannot_create_duplicate_po(po_setup):
    client = po_setup["client"]
    payload = po_setup["payload"]

    response = client.post(
        "/api/purchase-orders/",
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert PurchaseOrder.objects.count() == 1


@pytest.mark.django_db
def test_employee_cannot_create_po(po_setup, employee):
    client = APIClient()
    client.force_authenticate(user=employee)

    response = client.post(
        "/api/purchase-orders/",
        po_setup["payload"],
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_employee_cannot_receive(po_setup, employee):
    client = APIClient()
    client.force_authenticate(user=employee)

    po = po_setup["po"]
    item = po_setup["po_item"]

    response = receive(client, po, item, 5)

    assert response.status_code == 403
    assert Receiving.objects.count() == 0


@pytest.mark.django_db
def test_other_company_cannot_access_po(
    po_setup,
    other_employee,
):
    client = APIClient()
    client.force_authenticate(user=other_employee)

    po = po_setup["po"]

    response = client.get(
        f"/api/purchase-orders/{po.id}/"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_cannot_receive_duplicate_items(po_setup):
    client = po_setup["client"]
    po = po_setup["po"]
    item = po_setup["po_item"]

    response = client.post(
        f"/api/purchase-orders/{po.id}/receive/",
        {
            "items": [
                {
                    "purchase_order_item_id": item.id,
                    "received_quantity": 3,
                },
                {
                    "purchase_order_item_id": item.id,
                    "received_quantity": 3,
                },
            ]
        },
        format="json",
    )

    assert response.status_code == 400
    assert Receiving.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_receiving_does_not_exceed_ordered_quantity(
    procurement_officer,
    supplier_a,
):
    # Create an approved PR
    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Concurrent receiving test",
        status=PurchaseRequest.Status.APPROVED,
    )

    pr_item = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=10,
        estimated_unit_price=Decimal("450.00"),
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline="2026-12-01T12:00:00Z",
        status=RFQ.Status.SENT,
    )

    quote = SupplierQuote.objects.create(
        rfq=rfq,
        supplier=supplier_a,
        total_amount=Decimal("5000.00"),
        delivery_days=7,
        status=SupplierQuote.Status.SELECTED,
    )

    client = APIClient()
    client.force_authenticate(user=procurement_officer)

    response = client.post(
        "/api/purchase-orders/",
        {
            "selected_quote_id": quote.id,
            "expected_delivery_date": "2026-12-15",
            "items": [{
                "purchase_request_item_id": pr_item.id,
                "ordered_quantity": 10,
                "unit_price": "500.00",
            }],
        },
        format="json",
    )

    assert response.status_code == 201, response.data

    po = PurchaseOrder.objects.get(pk=response.data["id"])
    po_item = po.items.get()

    barrier = Barrier(2)

    def attempt_receiving(quantity):
        close_old_connections()

        try:
            thread_client = APIClient()
            thread_client.force_authenticate(
                user=procurement_officer
            )

            barrier.wait(timeout=10)

            result = thread_client.post(
                f"/api/purchase-orders/{po.id}/receive/",
                {
                    "items": [{
                        "purchase_order_item_id": po_item.id,
                        "received_quantity": quantity,
                    }]
                },
                format="json",
            )

            return result.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(attempt_receiving, 7)
        future_b = executor.submit(attempt_receiving, 5)

        results = [
            future_a.result(timeout=20),
            future_b.result(timeout=20),
        ]

    assert sorted(results) == [201, 400]

    total_received = sum(
        item.received_quantity
        for item in ReceivingItem.objects.filter(
            purchase_order_item=po_item
        )
    )

    assert total_received in [5, 7]
    assert total_received <= 10

    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED
