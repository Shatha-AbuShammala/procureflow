import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.procurement.models import PurchaseRequest, RFQ, SupplierQuote


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def approved_pr(company, employee):
    return PurchaseRequest.objects.create(
        company=company,
        requester=employee,
        title="Office Equipment",
        description="Equipment for development team",
        status=PurchaseRequest.Status.APPROVED,
    )


@pytest.fixture
def draft_pr(company, employee):
    return PurchaseRequest.objects.create(
        company=company,
        requester=employee,
        title="Draft Request",
        description="Not approved yet",
        status=PurchaseRequest.Status.DRAFT,
    )


@pytest.fixture
def rfq_data(approved_pr, supplier_a, supplier_b):
    return {
        "purchase_request": approved_pr.id,
        "suppliers": [
            supplier_a.id,
            supplier_b.id,
        ],
        "deadline": (
            timezone.now() + timedelta(days=7)
        ).isoformat(),
    }


@pytest.mark.django_db
def test_procurement_officer_can_create_rfq(
    api_client,
    procurement_officer,
    rfq_data,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    response = api_client.post(
        "/api/rfqs/",
        rfq_data,
        format="json",
    )

    assert response.status_code == 201

    rfq = RFQ.objects.get(
        id=response.data["id"]
    )

    assert rfq.status == RFQ.Status.DRAFT
    assert rfq.created_by == procurement_officer
    assert rfq.suppliers.count() == 2


@pytest.mark.django_db
def test_cannot_create_rfq_before_approval(
    api_client,
    procurement_officer,
    draft_pr,
    supplier_a,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    data = {
        "purchase_request": draft_pr.id,
        "suppliers": [supplier_a.id],
        "deadline": (
            timezone.now() + timedelta(days=7)
        ).isoformat(),
    }

    response = api_client.post(
        "/api/rfqs/",
        data,
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_cannot_use_supplier_from_other_company(
    api_client,
    procurement_officer,
    approved_pr,
    supplier_a,
    other_supplier,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    data = {
        "purchase_request": approved_pr.id,
        "suppliers": [
            supplier_a.id,
            other_supplier.id,
        ],
        "deadline": (
            timezone.now() + timedelta(days=7)
        ).isoformat(),
    }

    response = api_client.post(
        "/api/rfqs/",
        data,
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_can_send_rfq(
    api_client,
    procurement_officer,
    rfq_data,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    create_response = api_client.post(
        "/api/rfqs/",
        rfq_data,
        format="json",
    )

    rfq_id = create_response.data["id"]

    response = api_client.post(
        f"/api/rfqs/{rfq_id}/send/"
    )

    assert response.status_code == 200

    rfq = RFQ.objects.get(id=rfq_id)

    assert rfq.status == RFQ.Status.SENT


@pytest.mark.django_db
def test_invited_supplier_quote_can_be_created(
    api_client,
    procurement_officer,
    rfq_data,
    supplier_a,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    create_response = api_client.post(
        "/api/rfqs/",
        rfq_data,
        format="json",
    )

    rfq_id = create_response.data["id"]

    api_client.post(
        f"/api/rfqs/{rfq_id}/send/"
    )

    quote_data = {
        "rfq": rfq_id,
        "supplier": supplier_a.id,
        "total_amount": "4200.00",
        "currency": "USD",
        "delivery_days": 10,
        "payment_terms": "Net 30",
        "warranty": "1 year",
    }

    response = api_client.post(
        "/api/quotes/",
        quote_data,
        format="json",
    )

    assert response.status_code == 201

    quote = SupplierQuote.objects.get(
        id=response.data["id"]
    )

    assert quote.supplier == supplier_a
    assert quote.status == SupplierQuote.Status.SUBMITTED


@pytest.mark.django_db
def test_uninvited_supplier_cannot_submit_quote(
    api_client,
    procurement_officer,
    approved_pr,
    supplier_a,
    supplier_b,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    # RFQ فيها Supplier A فقط
    data = {
        "purchase_request": approved_pr.id,
        "suppliers": [supplier_a.id],
        "deadline": (
            timezone.now() + timedelta(days=7)
        ).isoformat(),
    }

    create_response = api_client.post(
        "/api/rfqs/",
        data,
        format="json",
    )

    rfq_id = create_response.data["id"]

    api_client.post(
        f"/api/rfqs/{rfq_id}/send/"
    )

    # Supplier B غير مدعو
    quote_data = {
        "rfq": rfq_id,
        "supplier": supplier_b.id,
        "total_amount": "3900.00",
        "currency": "USD",
        "delivery_days": 8,
    }

    response = api_client.post(
        "/api/quotes/",
        quote_data,
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_can_select_quote(
    api_client,
    procurement_officer,
    rfq_data,
    supplier_a,
    supplier_b,
):
    api_client.force_authenticate(
        user=procurement_officer
    )

    # Create RFQ
    create_response = api_client.post(
        "/api/rfqs/",
        rfq_data,
        format="json",
    )

    rfq_id = create_response.data["id"]

    # Send RFQ
    api_client.post(
        f"/api/rfqs/{rfq_id}/send/"
    )

    # Quote A
    quote_a_response = api_client.post(
        "/api/quotes/",
        {
            "rfq": rfq_id,
            "supplier": supplier_a.id,
            "total_amount": "4200.00",
            "currency": "USD",
            "delivery_days": 10,
        },
        format="json",
    )

    # Quote B
    quote_b_response = api_client.post(
        "/api/quotes/",
        {
            "rfq": rfq_id,
            "supplier": supplier_b.id,
            "total_amount": "4000.00",
            "currency": "USD",
            "delivery_days": 20,
        },
        format="json",
    )

    quote_a_id = quote_a_response.data["id"]
    quote_b_id = quote_b_response.data["id"]

    # Select Quote B
    response = api_client.post(
        f"/api/rfqs/{rfq_id}/quotes/{quote_b_id}/select/"
    )

    assert response.status_code == 200

    quote_a = SupplierQuote.objects.get(
        id=quote_a_id
    )

    quote_b = SupplierQuote.objects.get(
        id=quote_b_id
    )

    rfq = RFQ.objects.get(
        id=rfq_id
    )

    assert quote_b.status == SupplierQuote.Status.SELECTED
    assert quote_a.status == SupplierQuote.Status.REJECTED
    assert rfq.status == RFQ.Status.CLOSED