from celery import shared_task
import logging
from django.core.management import call_command
from django.db import OperationalError
from kombu.exceptions import OperationalError as BrokerError
from django.utils import timezone
from datetime import timedelta
from .models import Notification

logger = logging.getLogger(__name__)


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
    notification, created = Notification.objects.get_or_create(
        event_key=event_key,
        defaults={
            "recipient_id": recipient_id,
            "title": title,
            "message": message,
        },
    )

    return {
        "notification_id": notification.id,
        "created": created,
    }


@shared_task(
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_purchase_order_notification(po_id):
    from apps.procurement.models import PurchaseOrder

    po = PurchaseOrder.objects.select_related("created_by", "purchase_request").get(
        pk=po_id
    )
    if (
        not po.created_by.is_active
        or po.created_by.company_id != po.purchase_request.company_id
    ):
        return {"created": False, "notification_id": None}

    event_key = f"purchase-order-created:{po.id}:" f"recipient:{po.created_by_id}"

    result = create_notification_task(
        recipient_id=po.created_by_id,
        title="Purchase Order Created",
        message=f"Purchase order {po.order_number} was created.",
        event_key=event_key,
    )

    return result


def dispatch_purchase_order_notification(po_id):
    """Broker failure must not turn a committed order into HTTP 500."""
    try:
        send_purchase_order_notification.delay(po_id)
    except (BrokerError, OSError):
        logger.warning(
            "Broker unavailable for purchase order %s; creating notification locally",
            po_id,
        )
        send_purchase_order_notification(po_id)


@shared_task(
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def remind_expiring_rfqs():
    from apps.procurement.models import RFQ

    now = timezone.now()
    deadline_limit = now + timedelta(hours=24)

    rfqs = RFQ.objects.filter(
        status=RFQ.Status.SENT,
        deadline__gt=now,
        deadline__lte=deadline_limit,
        created_by__is_active=True,
    ).select_related("created_by", "purchase_request")

    created_count = 0

    for rfq in rfqs.iterator():
        if rfq.created_by.company_id != rfq.purchase_request.company_id:
            continue
        event_key = (
            f"rfq-deadline-reminder:{rfq.id}:" f"deadline:{rfq.deadline.isoformat()}"
        )

        result = create_notification_task(
            recipient_id=rfq.created_by_id,
            title="RFQ Deadline Reminder",
            message=(f"RFQ #{rfq.id} deadline is approaching."),
            event_key=event_key,
        )

        if result["created"]:
            created_count += 1

    return created_count


@shared_task
def flush_expired_tokens():
    call_command("flushexpiredtokens", verbosity=0)
