from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="room_profile")
    nickname = models.CharField(max_length=150)
    demo_key = models.CharField(max_length=80, null=True, unique=True, editable=False)
