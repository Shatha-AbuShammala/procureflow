
from django.db import transaction

from .models import AuditLog


def log_action(
    *,
    actor,
    action,
    entity,
    old_values=None,
    new_values=None,
):
    """
    Record an audit event for an important business operation.

    Call this function inside the same database transaction
    as the business operation.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "Audit logging must run inside transaction.atomic()."
        )

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity._meta.label,
        entity_id=str(entity.pk),
        old_values=old_values or {},
        new_values=new_values or {},
    )
