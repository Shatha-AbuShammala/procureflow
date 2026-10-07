import pytest
from rest_framework.test import APIClient
from apps.procurement.models import PurchaseRequest


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def pr_data():
    return {
        "title": "Office Equipment",
        "description": "Equipment for development team",
        "items": [
            {
                "item_name": "Laptop",
                "description": "Development laptop",
                "quantity": 3,
                "estimated_unit_price": "1000.00",
            },
            {
                "item_name": "Monitor",
                "description": "27 inch monitor",
                "quantity": 5,
                "estimated_unit_price": "300.00",
            },
        ],
    }


@pytest.mark.django_db
def test_employee_can_create_purchase_request(
    api_client,
    employee,
    pr_data,
):
    api_client.force_authenticate(user=employee)

    response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == PurchaseRequest.Status.DRAFT

    pr = PurchaseRequest.objects.get(id=response.data["id"])

    assert pr.requester == employee
    assert pr.company == employee.company
    assert pr.items.count() == 2


@pytest.mark.django_db
def test_employee_can_submit_purchase_request(
    api_client,
    employee,
    pr_data,
):
    api_client.force_authenticate(user=employee)

    create_response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    pr_id = create_response.data["id"]

    response = api_client.post(
        f"/api/purchase-requests/{pr_id}/submit/"
    )

    assert response.status_code == 200

    pr = PurchaseRequest.objects.get(id=pr_id)

    assert pr.status == PurchaseRequest.Status.PENDING_APPROVAL


@pytest.mark.django_db
def test_employee_cannot_approve_purchase_request(
    api_client,
    employee,
    pr_data,
):
    api_client.force_authenticate(user=employee)

    create_response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    pr_id = create_response.data["id"]

    api_client.post(
        f"/api/purchase-requests/{pr_id}/submit/"
    )

    response = api_client.post(
        f"/api/purchase-requests/{pr_id}/approve/"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_approve_purchase_request(
    api_client,
    employee,
    manager,
    pr_data,
):
    # Ahmed creates the PR
    api_client.force_authenticate(user=employee)

    create_response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    pr_id = create_response.data["id"]

    api_client.post(
        f"/api/purchase-requests/{pr_id}/submit/"
    )

    # Now Sara logs in
    api_client.force_authenticate(user=manager)

    response = api_client.post(
        f"/api/purchase-requests/{pr_id}/approve/"
    )

    assert response.status_code == 200

    pr = PurchaseRequest.objects.get(id=pr_id)

    assert pr.status == PurchaseRequest.Status.APPROVED
    assert pr.approval.approver == manager


@pytest.mark.django_db
def test_cannot_approve_already_approved_request(
    api_client,
    employee,
    manager,
    pr_data,
):
    api_client.force_authenticate(user=employee)

    create_response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    pr_id = create_response.data["id"]

    api_client.post(
        f"/api/purchase-requests/{pr_id}/submit/"
    )

    api_client.force_authenticate(user=manager)

    first_response = api_client.post(
        f"/api/purchase-requests/{pr_id}/approve/"
    )

    second_response = api_client.post(
        f"/api/purchase-requests/{pr_id}/approve/"
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400


@pytest.mark.django_db
def test_other_company_cannot_access_purchase_request(
    api_client,
    employee,
    other_employee,
    pr_data,
):
    # TechNova employee creates PR
    api_client.force_authenticate(user=employee)

    create_response = api_client.post(
        "/api/purchase-requests/",
        pr_data,
        format="json",
    )

    pr_id = create_response.data["id"]

    # Alpha employee tries to access it
    api_client.force_authenticate(user=other_employee)

    response = api_client.get(
        f"/api/purchase-requests/{pr_id}/"
    )

    assert response.status_code == 404