from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.procurement.models import PurchaseRequest, RFQ, SupplierQuote
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/me/",
        "/api/auth/company-users/",
        "/api/company/",
        "/api/suppliers/",
        "/api/purchase-requests/",
        "/api/rfqs/",
        "/api/quotes/",
        "/api/purchase-orders/",
    ],
)
def test_protected_endpoints_require_jwt(api_client, path):
    assert api_client.get(path).status_code == 401


def test_registration_validates_password_and_ignores_privilege_fields(
    api_client, company
):
    weak = api_client.post(
        "/api/auth/register/",
        {"username": "new", "password": "12345678"},
        format="json",
    )
    assert weak.status_code == 400
    good = api_client.post(
        "/api/auth/register/",
        {
            "username": "new",
            "password": "Uncommon-register-pass-17!",
            "company": company.pk,
            "role": "ADMIN",
            "is_staff": True,
            "is_superuser": True,
        },
        format="json",
    )
    assert good.status_code == 201
    user = User.objects.get(username="new")
    assert user.check_password("Uncommon-register-pass-17!")
    assert user.company_id is None and user.role == User.Role.EMPLOYEE
    assert not user.is_staff and not user.is_superuser
    assert "password" not in good.data


def login(api_client, user):
    response = api_client.post(
        "/api/auth/login/",
        {"username": user.username, "password": "StrongPass123!"},
        format="json",
    )
    assert response.status_code == 200, response.data
    return response.data


def test_real_jwt_login_rotation_and_replay_rejection(api_client, employee):
    tokens = login(api_client, employee)
    api_client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
    assert api_client.get("/api/auth/me/").data["id"] == employee.pk
    rotated = api_client.post(
        "/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert rotated.status_code == 200 and "refresh" in rotated.data
    assert (
        api_client.post(
            "/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/auth/refresh/", {"refresh": rotated.data["refresh"]}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.parametrize("change", ["deactivate", "password", "delete"])
def test_tokens_fail_after_account_changes(api_client, employee, change):
    tokens = login(api_client, employee)
    if change == "delete":
        employee.delete()
    else:
        if change == "deactivate":
            employee.is_active = False
        else:
            employee.set_password("Completely-different-password-23!")
        employee.save()
    api_client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
    assert api_client.get("/api/auth/me/").status_code == 401
    assert (
        api_client.post(
            "/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
        ).status_code
        == 401
    )


def test_expired_and_invalid_tokens_rejected(api_client, employee):
    token = AccessToken.for_user(employee)
    token.set_exp(lifetime=timedelta(seconds=-1))
    for value in [str(token), "invalid.token.value"]:
        api_client.credentials(HTTP_AUTHORIZATION="Bearer " + value)
        assert api_client.get("/api/auth/me/").status_code == 401


def test_login_is_throttled(api_client):
    for _ in range(10):
        assert (
            api_client.post(
                "/api/auth/login/",
                {"username": "missing", "password": "bad"},
                format="json",
            ).status_code
            == 401
        )
    assert (
        api_client.post(
            "/api/auth/login/",
            {"username": "missing", "password": "bad"},
            format="json",
        ).status_code
        == 429
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/purchase-requests/",
        "/api/purchase-orders/",
        "/api/suppliers/",
        "/api/rfqs/",
        "/api/quotes/",
    ],
)
def test_users_without_company_are_denied(api_client, unassigned_user, path):
    api_client.force_authenticate(unassigned_user)
    assert api_client.get(path).status_code == 403
    assert api_client.post(path, {}, format="json").status_code == 403


@pytest.mark.parametrize("kind", ["supplier", "rfq", "quote", "company-user"])
def test_other_company_cannot_read_or_change_records(
    api_client,
    workflow,
    other_procurement_officer,
    other_company,
    supplier_a,
    company_admin,
    employee,
    kind,
):
    other_procurement_officer.role = User.Role.ADMIN
    other_procurement_officer.save()
    api_client.force_authenticate(other_procurement_officer)
    paths = {
        "supplier": f"/api/suppliers/{supplier_a.pk}/",
        "rfq": f"/api/rfqs/{workflow['rfq'].pk}/",
        "quote": f"/api/quotes/{workflow['quotes'][0].pk}/",
        "company-user": f"/api/auth/company-users/{employee.pk}/",
    }
    path = paths[kind]
    assert api_client.get(path).status_code == 404
    if kind in {"supplier", "company-user"}:
        assert (
            api_client.patch(
                path, {"name": "stolen", "username": "stolen"}, format="json"
            ).status_code
            == 404
        )
    assert api_client.get("/api/company/").data["id"] == other_company.pk


def test_quote_creation_cannot_write_to_another_company(
    api_client, workflow, other_procurement_officer, supplier_a
):
    # Both foreign keys are internally consistent, but belong to another tenant.
    api_client.force_authenticate(other_procurement_officer)
    workflow["quotes"][0].delete()
    response = api_client.post(
        "/api/quotes/",
        {
            "rfq": workflow["rfq"].pk,
            "supplier": supplier_a.pk,
            "total_amount": "250.00",
            "delivery_days": 3,
        },
        format="json",
    )
    assert response.status_code == 400
    assert not SupplierQuote.objects.filter(
        rfq=workflow["rfq"], supplier=supplier_a
    ).exists()


def test_rfq_creation_cannot_reference_foreign_request(
    api_client, workflow, other_procurement_officer, other_supplier
):
    workflow["rfq"].delete()
    api_client.force_authenticate(other_procurement_officer)
    response = api_client.post(
        "/api/rfqs/",
        {
            "purchase_request": workflow["pr"].pk,
            "suppliers": [other_supplier.pk],
            "deadline": (timezone.now() + timedelta(days=5)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 400
    assert not RFQ.objects.filter(purchase_request=workflow["pr"]).exists()


def test_employee_can_only_see_own_requests(api_client, employee, company, workflow):
    colleague = User.objects.create_user(username="colleague", company=company)
    hidden = PurchaseRequest.objects.create(
        company=company, requester=colleague, title="Private"
    )
    api_client.force_authenticate(employee)
    assert api_client.get(f"/api/purchase-requests/{hidden.pk}/").status_code == 404
    assert [pr["id"] for pr in api_client.get("/api/purchase-requests/").data] == [
        workflow["pr"].pk
    ]


def test_company_admin_cannot_escalate_user_privileges(
    api_client, company_admin, employee, other_company
):
    api_client.force_authenticate(company_admin)
    response = api_client.patch(
        f"/api/auth/company-users/{employee.pk}/",
        {
            "company": other_company.pk,
            "role": "ADMIN",
            "is_staff": True,
            "is_superuser": True,
            "password": "Changed-password-56!",
        },
        format="json",
    )
    assert response.status_code == 200
    employee.refresh_from_db()
    assert employee.company_id == company_admin.company_id
    assert employee.role == User.Role.EMPLOYEE and not employee.is_staff
    assert not employee.is_superuser and employee.check_password("StrongPass123!")


def test_tenant_staff_cannot_use_platform_admin(client, company_admin):
    company_admin.is_staff = True
    company_admin.save()
    client.force_login(company_admin)
    assert client.get("/admin/").status_code == 302


def test_attachments_are_private_and_force_download(
    api_client,
    workflow,
    procurement_officer,
    other_procurement_officer,
    supplier_a,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    workflow["quotes"][0].delete()
    api_client.force_authenticate(procurement_officer)
    response = api_client.post(
        "/api/quotes/",
        {
            "rfq": workflow["rfq"].pk,
            "supplier": supplier_a.pk,
            "total_amount": "250.00",
            "delivery_days": 3,
            "attachment": SimpleUploadedFile(
                "offer.pdf", b"%PDF-1.7\nexample", content_type="application/pdf"
            ),
        },
        format="multipart",
    )
    assert response.status_code == 201, response.data
    url = f"/api/quotes/{response.data['id']}/attachment/"
    download = api_client.get(url)
    assert download.status_code == 200
    assert "attachment" in download["Content-Disposition"]
    assert b"%PDF-" in b"".join(download.streaming_content)
    assert api_client.get("/media/quotes/offer.pdf").status_code == 404
    api_client.force_authenticate(other_procurement_officer)
    assert api_client.get(url).status_code == 404
    api_client.force_authenticate(None)
    assert api_client.get(url).status_code == 401


def test_html_upload_rejected(
    api_client, workflow, procurement_officer, supplier_a, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    workflow["quotes"][0].delete()
    api_client.force_authenticate(procurement_officer)
    response = api_client.post(
        "/api/quotes/",
        {
            "rfq": workflow["rfq"].pk,
            "supplier": supplier_a.pk,
            "total_amount": "250.00",
            "delivery_days": 3,
            "attachment": SimpleUploadedFile(
                "offer.pdf", b"<html>executable content</html>"
            ),
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert not list(tmp_path.iterdir())


def test_supplier_with_history_returns_validation_error(
    api_client, workflow, supplier_a, procurement_officer
):
    api_client.force_authenticate(procurement_officer)
    assert api_client.delete(f"/api/suppliers/{supplier_a.pk}/").status_code == 400
    assert Supplier.objects.filter(pk=supplier_a.pk).exists()


@pytest.mark.parametrize("role", ["employee", "manager"])
@pytest.mark.parametrize(
    "path", ["/api/suppliers/", "/api/rfqs/", "/api/quotes/", "/api/purchase-orders/"]
)
def test_procurement_writes_enforce_roles(api_client, request, role, path):
    api_client.force_authenticate(request.getfixturevalue(role))
    assert api_client.post(path, {}, format="json").status_code == 403


def test_foreign_manager_cannot_approve_request(
    api_client, workflow, other_procurement_officer
):
    other_procurement_officer.role = User.Role.MANAGER
    other_procurement_officer.save()
    pr = workflow["pr"]
    pr.status = PurchaseRequest.Status.PENDING_APPROVAL
    pr.save()
    api_client.force_authenticate(other_procurement_officer)
    assert (
        api_client.post(f"/api/purchase-requests/{pr.pk}/approve/").status_code == 404
    )
    pr.refresh_from_db()
    assert pr.status == PurchaseRequest.Status.PENDING_APPROVAL


def test_manager_cannot_approve_own_request(api_client, workflow, employee):
    employee.role = User.Role.MANAGER
    employee.save()
    pr = workflow["pr"]
    pr.status = PurchaseRequest.Status.PENDING_APPROVAL
    pr.save()
    api_client.force_authenticate(employee)
    assert (
        api_client.post(f"/api/purchase-requests/{pr.pk}/approve/").status_code == 403
    )
