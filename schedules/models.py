from django.conf import settings
from django.db import models
from django.db.models import Q, F


class CalendarLock(models.Model):
    """Single-room schedule writes serialize overlap checks, including empty calendars."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="schedule_single_calendar")]


class Schedule(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=4000)
    category = models.CharField(max_length=80, default="general")
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="room_schedules")
    is_cancelled = models.BooleanField(default=False)
    recruitment_capacity = models.PositiveIntegerField(null=True, blank=True)
    # Stable seed identity is independent of editable title and time.
    demo_key = models.CharField(max_length=80, null=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(starts_at__lt=F("ends_at")), name="schedule_positive_interval"),
            models.CheckConstraint(condition=Q(recruitment_capacity__isnull=True) | Q(recruitment_capacity__gte=1), name="schedule_positive_capacity"),
        ]


class Participation(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="participations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["schedule", "user"], name="schedule_unique_participant")]
