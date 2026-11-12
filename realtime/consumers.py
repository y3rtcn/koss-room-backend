import json
from importlib import import_module

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user
from django.http import HttpRequest

from attendance.services import status
from chat.services import save_message
from common.http import ApiError

from .events import ROOM_GROUP


@database_sync_to_async
def current_session_user(session_key):
    request = HttpRequest()
    request.session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)
    return get_user(request)


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.joined = False
        self.user = self.scope["user"]
        if not self.user.is_authenticated or not self.user.is_active:
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(ROOM_GROUP, self.channel_name)
        self.joined = True
        await self.accept()
        await self.send_json({"type": "connected", "data": await database_sync_to_async(status)(self.user)})

    async def disconnect(self, code):
        if self.joined:
            await self.channel_layer.group_discard(ROOM_GROUP, self.channel_name)
        # 연결 종료는 퇴실이 아닙니다.

    async def still_authenticated(self):
        user = await current_session_user(self.scope["session"].session_key)
        if not user.is_authenticated or not user.is_active or user.pk != self.user.pk:
            await self.close(code=4401)
            return False
        self.user = user
        return True

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        size = len(text_data.encode("utf-8")) if text_data is not None else len(bytes_data or b"")
        if size > 16 * 1024:
            await self.close(code=1009)
            return
        if not await self.still_authenticated():
            return
        try:
            if text_data is None:
                raise ApiError("invalid_json", "JSON 텍스트 프레임을 사용하세요.")
            try:
                data = json.loads(text_data)
            except ValueError:
                raise ApiError("invalid_json", "올바른 JSON 객체가 필요합니다.")
            if not isinstance(data, dict):
                raise ApiError("invalid_json", "JSON 객체가 필요합니다.")
            if data.get("type") == "ping":
                await self.send_json({"type": "pong"})
            elif data.get("type") == "chat.send":
                message, created = await database_sync_to_async(save_message)(self.user, data)
                await self.send_json({"type": "chat.ack", "data": {"message": message, "created": created}})
            else:
                raise ApiError("unknown_type", "chat.send 또는 ping을 사용하세요.")
        except ApiError as exc:
            await self.send_json({"type": "error", "error": {"code": exc.code, "message": exc.message}})

    async def room_event(self, event):
        if await self.still_authenticated():
            await self.send_json(event["event"])
