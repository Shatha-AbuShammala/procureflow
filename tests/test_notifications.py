
from datetime import timedelta
from unittest.mock import patch
from django.db import transaction
import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.tasks import (
    create_notification_task,
    remind_expiring_rfqs,
)
from apps.procurement.models import PurchaseRequest, RFQ


@pytest.mark.django_db
def test_notification_is_created(employee):
    """A notification should be saved for its recipient."""

    result = create_notification_task(
        recipient_id=employee.id,
        title="Test Notification",
        message="Hello",
        event_key="test-event-1",
    )

    assert result["created"] is True

    assert Notification.objects.filter(
        recipient=employee,
        event_key="test-event-1",
    ).count() == 1


@pytest.mark.django_db
def test_notification_is_idempotent(employee):
    """Running the same task twice must not duplicate notifications."""

    first = create_notification_task(
        recipient_id=employee.id,
        title="Test",
        message="Hello",
        event_key="same-event",
    )

    second = create_notification_task(
        recipient_id=employee.id,
        title="Test",
        message="Hello",
        event_key="same-event",
    )

    assert first["created"] is True
    assert second["created"] is False

    assert Notification.objects.filter(
        event_key="same-event"
    ).count() == 1


@pytest.mark.django_db
def test_notification_belongs_to_correct_user(
    employee,
    other_employee,
):
    """Only the intended recipient should receive the notification."""

    create_notification_task(
        recipient_id=employee.id,
        title="Test",
        message="Hello",
        event_key="user-isolation-event",
    )

    assert Notification.objects.filter(
        recipient=employee
    ).count() == 1

    assert Notification.objects.filter(
        recipient=other_employee
    ).count() == 0


@pytest.mark.django_db
def test_remind_expiring_rfqs(procurement_officer):
    """An RFQ nearing its deadline should generate one reminder."""

    pr = PurchaseRequest.objects.create(
        company=procurement_officer.company,
        requester=procurement_officer,
        title="Test RFQ reminder",
        status=PurchaseRequest.Status.APPROVED,
    )

    rfq = RFQ.objects.create(
        purchase_request=pr,
        created_by=procurement_officer,
        deadline=timezone.now() + timedelta(hours=12),
        status=RFQ.Status.SENT,
    )

    first_result = remind_expiring_rfqs()
    second_result = remind_expiring_rfqs()

    assert first_result == 1
    assert second_result == 0

    assert Notification.objects.filter(
        recipient=procurement_officer,
        event_key__startswith=(
            f"rfq-deadline-reminder:{rfq.id}:"
        ),
    ).count() == 1


from unittest.mock import patch
from django.db import transaction


@pytest.mark.django_db
def test_notification_dispatched_only_after_commit(
    django_capture_on_commit_callbacks,
):
    dispatched = []

    with patch(
        "apps.notifications.tasks.create_notification_task.delay",
        side_effect=lambda **kwargs: dispatched.append(kwargs),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            transaction.on_commit(
                lambda: create_notification_task.delay(
                    recipient_id=1,
                    title="Purchase Order Created",
                    message="A purchase order was created.",
                    event_key="po-commit-test",
                )
            )

            assert dispatched == []

    assert len(dispatched) == 1
    assert dispatched[0]["event_key"] == "po-commit-test"
