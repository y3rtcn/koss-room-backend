from django.conf import settings
from django.db import models


class Schedule(models.Model):
    title = models.CharField(max_length=100)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_schedules",
    )
    space = models.ForeignKey(
        "spaces.Space",
        on_delete=models.PROTECT,
        related_name="schedules",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    expected_count = models.PositiveIntegerField()
    purpose = models.CharField(max_length=100)
    is_cancelled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="schedules_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(expected_count__gte=1),
                name="schedules_expected_count_positive",
            ),
        ]

    def __str__(self):
        return self.title

# Create your models here.
