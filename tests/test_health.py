from unittest.mock import patch

import pytest
from django.db import OperationalError
from redis import ConnectionError


def test_liveness_is_public(client):
    response = client.get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_checks_database_and_redis(client):
    with patch("apps.core.views.Redis.from_url") as redis:
        redis.return_value.__enter__.return_value.ping.return_value = True
        response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True}


@pytest.mark.django_db
def test_readiness_returns_503_without_exposing_errors(client):
    with patch(
        "apps.core.views.connection.cursor",
        side_effect=OperationalError("secret database address"),
    ), patch(
        "apps.core.views.Redis.from_url",
        side_effect=ConnectionError("secret broker address"),
    ):
        response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False, "redis": False}
    assert b"secret" not in response.content
