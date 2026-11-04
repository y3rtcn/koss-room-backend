from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Table(models.Model):
    name = models.CharField(max_length=80)
    capacity = models.PositiveIntegerField()
    demo_key = models.CharField(max_length=80, null=True, unique=True, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(capacity__gte=1), name="table_positive_capacity")]


class TableUse(models.Model):
    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="uses")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="room_table_uses")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(ended_at__isnull=True), name="table_one_active_use_per_user"),
            models.CheckConstraint(condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")), name="table_valid_use_interval"),
        ]
