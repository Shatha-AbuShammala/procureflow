import logging

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe
from redis import Redis, RedisError

logger = logging.getLogger(__name__)


@require_safe
def live(request):
    return JsonResponse({"status": "ok"})


@require_safe
def ready(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = True
    except DatabaseError:
        checks["database"] = False
        logger.error("Readiness check failed: database")
    try:
        with Redis.from_url(
            settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            checks["redis"] = bool(client.ping())
    except (RedisError, ValueError):
        checks["redis"] = False
        logger.error("Readiness check failed: redis")
    healthy = all(checks.values())
    response = JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
    response["Cache-Control"] = "no-store"
    return response
