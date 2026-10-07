import pytest
from django.contrib.auth import get_user_model
from apps.suppliers.models import Supplier

from apps.companies.models import Company


User = get_user_model()


@pytest.fixture
def company():
    return Company.objects.create(
        name="TechNova"
    )


@pytest.fixture
def other_company():
    return Company.objects.create(
        name="Alpha"
    )


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