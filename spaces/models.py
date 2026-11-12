from django.db import models


class Space(models.Model):
    name = models.CharField(max_length=50, unique=True)
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacity__gte=1),
                name="spaces_capacity_at_least_one",
            ),
        ]

    def __str__(self):
        return self.name

# Create your models here.
