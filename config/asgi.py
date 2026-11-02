import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_application = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.urls import path

from realtime.consumers import RoomConsumer

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": OriginValidator(
        AuthMiddlewareStack(URLRouter([path("ws/room/", RoomConsumer.as_asgi())])),
        settings.WS_ALLOWED_ORIGINS,
    ),
})
