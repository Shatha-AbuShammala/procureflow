import pytest
from django.contrib.auth import get_user_model
from apps.suppliers.models import Supplier

from apps.companies.models import Company
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    RFQ,
    SupplierQuote,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def isolated_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def company_admin(company):
    return User.objects.create_user(
        username="company_admin",
        password="StrongPass123!",
        company=company,
        role=User.Role.ADMIN,
    )


@pytest.fixture
def other_procurement_officer(other_company):
    return User.objects.create_user(
        username="other_procurement",
        password="StrongPass123!",
        company=other_company,
        role=User.Role.PROCUREMENT_OFFICER,
    )


@pytest.fixture
def unassigned_user():
    return User.objects.create_user(username="unassigned", password="StrongPass123!")


@pytest.fixture
def workflow(employee, procurement_officer, supplier_a, supplier_b):
    pr = PurchaseRequest.objects.create(
        company=employee.company,
        requester=employee,
        title="Equipment",
        status=PurchaseRequest.Status.APPROVED,
    )
    first = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Laptop",
        quantity=2,
        estimated_unit_price="100.00",
    )
    second = PurchaseRequestItem.objects.create(
        purchase_request=pr,
        item_name="Monitor",
        quantity=1,
        estimated_unit_price="50.00",
    )
    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline=timezone.now() + timedelta(days=7),
        status=RFQ.Status.SENT,
    )
    rfq.suppliers.set([supplier_a, supplier_b])
    quote_a = SupplierQuote.objects.create(
        rfq=rfq, supplier=supplier_a, total_amount="250.00", delivery_days=7
    )
    quote_b = SupplierQuote.objects.create(
        rfq=rfq, supplier=supplier_b, total_amount="250.00", delivery_days=5
    )
    return {
        "pr": pr,
        "items": [first, second],
        "rfq": rfq,
        "quotes": [quote_a, quote_b],
    }


@pytest.fixture
def order_payload(workflow):
    rfq = workflow["rfq"]
    rfq.status = RFQ.Status.CLOSED
    rfq.save(update_fields=["status"])
    quote = workflow["quotes"][0]
    quote.status = SupplierQuote.Status.SELECTED
    quote.save(update_fields=["status"])
    return {
        "selected_quote_id": quote.pk,
        "expected_delivery_date": (
            timezone.localdate() + timedelta(days=10)
        ).isoformat(),
        "items": [
            {
                "purchase_request_item_id": workflow["items"][1].pk,
                "ordered_quantity": 1,
                "unit_price": "50.00",
            },
            {
                "purchase_request_item_id": workflow["items"][0].pk,
                "ordered_quantity": 2,
                "unit_price": "100.00",
            },
        ],
    }


@pytest.fixture
def company():
    return Company.objects.create(name="TechNova")


@pytest.fixture
def other_company():
    return Company.objects.create(name="Alpha")


@pytest.fixture
def employee(company):
    return User.objects.create_user(
        username="ahmed",
        password="StrongPass123!",
        company=company,
        role=User.Role.EMPLOYEE,
    )


@pytest.fixture
def manager(company):
    return User.objects.create_user(
        username="sara",
        password="StrongPass123!",
        company=company,
        role=User.Role.MANAGER,
    )


@pytest.fixture
def procurement_officer(company):
    return User.objects.create_user(
        username="omar_procurement",
        password="StrongPass123!",
        company=company,
        role=User.Role.PROCUREMENT_OFFICER,
    )


@pytest.fixture
def other_employee(other_company):
    return User.objects.create_user(
        username="ali",
        password="StrongPass123!",
        company=other_company,
        role=User.Role.EMPLOYEE,
    )


@pytest.fixture
def supplier_a(company):
    return Supplier.objects.create(
        company=company,
        name="Supplier A",
        email="supplierA@test.com",
        is_active=True,
    )


@pytest.fixture
def supplier_b(company):
    return Supplier.objects.create(
        company=company,
        name="Supplier B",
        email="supplierB@test.com",
        is_active=True,
    )


@pytest.fixture
def other_supplier(other_company):
    return Supplier.objects.create(
        company=other_company,
        name="Alpha Supplier",
        email="alpha@test.com",
        is_active=True,
    )
