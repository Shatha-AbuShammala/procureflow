
import pytest

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.audit.models import AuditLog
from apps.procurement.models import PurchaseRequest
from apps.procurement.views import PurchaseRequestViewSet


@pytest.fixture
def manager(employee):
    User = get_user_model()

    return User.objects.create_user(
        username="audit_manager",
        password="TestPass123!",
        company=employee.company,
        role=User.Role.MANAGER,
    )


@pytest.fixture
def pending_request(employee):
    return PurchaseRequest.objects.create(
        company=employee.company,
        requester=employee,
        title="Audit Integration Test",
        status=PurchaseRequest.Status.PENDING_APPROVAL,
    )


def perform_action(action, user, purchase_request):
    factory = APIRequestFactory()

    request = factory.post(
        f"/purchase-requests/{purchase_request.pk}/{action}/",
        {},
        format="json",
    )

    force_authenticate(request, user=user)

    view = PurchaseRequestViewSet.as_view({
        "post": action,
    })

    return view(request, pk=purchase_request.pk)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action,expected_status,expected_audit_action",
    [
        (
            "approve",
            PurchaseRequest.Status.APPROVED,
            AuditLog.Action.APPROVE,
        ),
        (
            "reject",
            PurchaseRequest.Status.REJECTED,
            AuditLog.Action.REJECT,
        ),
    ],
)
def test_approval_actions_create_audit_logs(
    manager,
    pending_request,
    action,
    expected_status,
    expected_audit_action,
):
    response = perform_action(
        action,
        manager,
        pending_request,
    )

    assert response.status_code == 200

    pending_request.refresh_from_db()
    assert pending_request.status == expected_status

    audit = AuditLog.objects.get(
        entity_type=pending_request._meta.label,
        entity_id=str(pending_request.pk),
        action=expected_audit_action,
    )

    assert audit.actor == manager
    assert audit.old_values["status"] == (
        PurchaseRequest.Status.PENDING_APPROVAL
    )
    assert audit.new_values["status"] == expected_status


@pytest.mark.django_db
def test_audit_failure_rolls_back_approval(
    manager,
    pending_request,
    monkeypatch,
):
    def failing_log_action(**kwargs):
        raise RuntimeError("Audit logging failed")

    monkeypatch.setattr(
        "apps.procurement.views.log_action",
        failing_log_action,
    )

    with pytest.raises(
        RuntimeError,
        match="Audit logging failed",
    ):
        perform_action(
            "approve",
            manager,
            pending_request,
        )

    pending_request.refresh_from_db()

    assert pending_request.status == (
        PurchaseRequest.Status.PENDING_APPROVAL
    )

    assert not AuditLog.objects.filter(
        entity_type=pending_request._meta.label,
        entity_id=str(pending_request.pk),
    ).exists()
