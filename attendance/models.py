from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Visit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="room_visits")
    entered_at = models.DateTimeField(db_index=True)
    exited_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(exited_at__isnull=True), name="attendance_one_open_visit"),
            models.CheckConstraint(condition=Q(exited_at__isnull=True) | Q(exited_at__gte=F("entered_at")), name="attendance_valid_interval"),
        ]


class OccupancyState(models.Model):
    """한 동아리방의 변경 순번과 쓰기 잠금. 인원은 Visit에서 계산합니다."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="attendance_single_room")]
