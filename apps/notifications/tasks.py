
from celery import shared_task
from django.db import OperationalError, IntegrityError
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from .models import Notification


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def create_notification_task(
    self,
    recipient_id,
    title,
    message,
    event_key,
):
    try:
        notification, created = Notification.objects.get_or_create(
            event_key=event_key,
            defaults={
                "recipient_id": recipient_id,
                "title": title,
                "message": message,
            },
        )
    except IntegrityError:
        # Unique event_key may have been inserted concurrently.
        notification = Notification.objects.get(
            event_key=event_key,
        )
        created = False

    return {
        "notification_id": notification.id,
        "created": created,
    }


@shared_task
def send_purchase_order_notification(po_id):
    from apps.procurement.models import PurchaseOrder

    po = PurchaseOrder.objects.select_related(
        "created_by"
    ).get(pk=po_id)

    event_key = (
        f"purchase-order-created:{po.id}:"
        f"recipient:{po.created_by_id}"
    )

    result = create_notification_task(
        recipient_id=po.created_by_id,
        title="Purchase Order Created",
        message=f"Purchase order {po.order_number} was created.",
        event_key=event_key,
    )

    return result

@shared_task
def remind_expiring_rfqs():
    from apps.procurement.models import RFQ

    now = timezone.now()
    deadline_limit = now + timedelta(hours=24)

    rfqs = (
        RFQ.objects.filter(
            status=RFQ.Status.SENT,
            deadline__gt=now,
            deadline__lte=deadline_limit,
        )
        .select_related("created_by")
    )

    created_count = 0

    for rfq in rfqs.iterator():
        event_key = (
            f"rfq-deadline-reminder:{rfq.id}:"
            f"deadline:{rfq.deadline.isoformat()}"
        )

        result = create_notification_task(
            recipient_id=rfq.created_by_id,
            title="RFQ Deadline Reminder",
            message=(
                f"RFQ #{rfq.id} deadline is approaching."
            ),
            event_key=event_key,
        )

        if result["created"]:
            created_count += 1

    return created_count

