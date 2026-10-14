
import pytest
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.companies.models import Company


@pytest.mark.django_db
def test_audit_log_created(employee):
    with transaction.atomic():
        log = log_action(
            actor=employee,
            action=AuditLog.Action.CREATE,
            entity=employee.company,
            new_values={"name": employee.company.name},
        )

    assert AuditLog.objects.filter(pk=log.pk).exists()
    assert log.actor == employee
    assert log.action == AuditLog.Action.CREATE
    assert log.entity_type == Company._meta.label


@pytest.mark.django_db
def test_audit_log_rollback(employee):
    with pytest.raises(ValueError):
        with transaction.atomic():
            log_action(
                actor=employee,
                action=AuditLog.Action.UPDATE,
                entity=employee.company,
                new_values={"name": "Changed"},
            )
            raise ValueError("Simulated failure")

    assert AuditLog.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_audit_log_requires_transaction(employee):
    with pytest.raises(
        RuntimeError,
        match="Audit logging must run inside transaction.atomic",
    ):
        log_action(
            actor=employee,
            action=AuditLog.Action.CREATE,
            entity=employee.company,
        )


