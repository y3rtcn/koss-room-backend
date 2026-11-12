from django.conf import settings
from django.db import models


class Message(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="room_messages")
    nickname = models.CharField(max_length=150)
    content = models.CharField(max_length=500)
    client_id = models.UUIDField()
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "client_id"], name="chat_unique_client_message")]
        ordering = ["id"]
