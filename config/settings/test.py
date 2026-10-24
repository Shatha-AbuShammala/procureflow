"""PostgreSQL tests with no broker dependency. Never use in deployment."""

import os

os.environ.setdefault(
    "DJANGO_SECRET_KEY", "test-only-secret-not-for-deployment-5c209b7ac6526a1782"
)
from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
