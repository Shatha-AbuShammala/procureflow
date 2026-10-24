import os
from pathlib import Path
import subprocess
import sys

import pytest


def production_env():
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "DJANGO_SECRET_KEY": "production-check-only-72a81cf652d93b8e7f9822c5431ff6bd51234",
        "DJANGO_ALLOWED_HOSTS": "procureflow.example.com",
        "CACHE_URL": "redis://127.0.0.1:6379/2",
        "DJANGO_TRUST_PROXY": "true",
    }


def run_check(env):
    return subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_production_deployment_checks():
    result = run_check(production_env())
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "variable,value",
    [
        ("DJANGO_SECRET_KEY", ""),
        ("DJANGO_SECRET_KEY", "short-secret"),
        ("DJANGO_ALLOWED_HOSTS", ""),
        ("DJANGO_ALLOWED_HOSTS", "*"),
        ("DJANGO_ALLOWED_HOSTS", " , "),
    ],
)
def test_production_rejects_unsafe_configuration(variable, value):
    env = production_env()
    env[variable] = value
    result = run_check(env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
