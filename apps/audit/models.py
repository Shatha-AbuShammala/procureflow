
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"
        DELETE = "DELETE", "Delete"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )

    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)

    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor", "created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.action} {self.entity_type}"
            f" #{self.entity_id}"
        )
