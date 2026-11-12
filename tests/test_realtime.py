from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.test import TransactionTestCase
from django.utils import timezone

from attendance.models import OccupancyState, Visit
from attendance.services import set_presence
from chat.models import Message
from chat.services import save_message
from config.asgi import application
from realtime.events import notify_schedule_change


class RealtimeTests(TransactionTestCase):
    def setUp(self):
        OccupancyState.objects.get_or_create(pk=1)
        self.user = get_user_model().objects.create_user(username="member", email="member@kookmin.ac.kr")
        self.client.force_login(self.user)
        self.session_key = self.client.session.session_key
        self.cookie = f"sessionid={self.session_key}".encode()

    def socket(self, *, origin=b"http://localhost:8000", cookie=True):
        headers = [(b"origin", origin)]
        if cookie:
            headers.append((b"cookie", self.cookie))
        return WebsocketCommunicator(application, "/ws/room/", headers=headers)

    def test_anonymous_and_foreign_origin_are_denied(self):
        async def run():
            for socket in (self.socket(cookie=False), self.socket(origin=b"https://evil.example")):
                connected, _ = await socket.connect()
                self.assertFalse(connected)
                await socket.disconnect()
        async_to_sync(run)()

    def test_full_authenticated_flow_and_reconnect(self):
        async def run():
            sender, receiver = self.socket(), self.socket()
            for socket in (sender, receiver):
                self.assertTrue((await socket.connect())[0])
                self.assertEqual((await socket.receive_json_from())["type"], "connected")
            await database_sync_to_async(set_presence)(self.user, inside=True)
            for socket in (sender, receiver):
                event = await socket.receive_json_from()
                self.assertEqual(event["type"], "attendance.updated")
                self.assertEqual(event["data"]["current_count"], 1)
            payload = {"type": "chat.send", "content": "실시간 메시지", "client_id": str(uuid4())}
            await sender.send_json_to(payload)
            replies = [await sender.receive_json_from(), await sender.receive_json_from()]
            self.assertEqual({reply["type"] for reply in replies}, {"chat.ack", "chat.message"})
            message_event = await receiver.receive_json_from()
            self.assertEqual(message_event["data"]["message"]["content"], payload["content"])
            await sender.send_json_to(payload)
            self.assertFalse((await sender.receive_json_from())["data"]["created"])
            self.assertTrue(await receiver.receive_nothing(timeout=0.05))
            await sender.disconnect()
            await receiver.disconnect()
            self.assertEqual(await database_sync_to_async(Visit.objects.filter(exited_at__isnull=True).count)(), 1)
            reconnect = self.socket()
            self.assertTrue((await reconnect.connect())[0])
            self.assertTrue((await reconnect.receive_json_from())["data"]["is_inside"])
            # 새 HTTP 클라이언트/재접속도 저장된 대화를 다시 조회합니다.
            history = await database_sync_to_async(self.client.get)("/api/chat/messages/")
            self.assertEqual(history.json()["messages"][0]["content"], payload["content"])
            await database_sync_to_async(set_presence)(self.user, inside=False)
            self.assertEqual((await reconnect.receive_json_from())["data"]["current_count"], 0)
            stats = await database_sync_to_async(self.client.get)("/api/analytics/daily/")
            self.assertEqual(stats.json()["visit_count"], 1)
            await reconnect.disconnect()
        async_to_sync(run)()
        self.assertEqual(Message.objects.count(), 1)

    def test_bad_frames_and_unknown_type(self):
        async def run():
            socket = self.socket()
            await socket.connect()
            await socket.receive_json_from()
            for payload in ("{", "[]", '{"type":"unknown"}', '{"type":"chat.send","content":" "}'):
                await socket.send_to(text_data=payload)
                self.assertEqual((await socket.receive_json_from())["type"], "error")
            await socket.send_to(bytes_data=b"binary")
            self.assertEqual((await socket.receive_json_from())["type"], "error")
            await socket.send_json_to({"type": "ping"})
            self.assertEqual((await socket.receive_json_from())["type"], "pong")
            await socket.send_to(text_data="x" * 16385)
            self.assertEqual((await socket.receive_output())["code"], 1009)
            await socket.disconnect()
        async_to_sync(run)()

    def test_logout_stops_existing_socket_sends(self):
        async def run():
            socket = self.socket()
            await socket.connect()
            await socket.receive_json_from()
            await database_sync_to_async(self.client.logout)()
            await socket.send_json_to({"type": "chat.send", "content": "blocked", "client_id": str(uuid4())})
            self.assertEqual((await socket.receive_output())["code"], 4401)
            await socket.disconnect()
        async_to_sync(run)()
        self.assertFalse(Message.objects.exists())

    def test_expired_session_stops_broadcast_reception(self):
        async def run():
            socket = self.socket()
            await socket.connect()
            await socket.receive_json_from()
            await database_sync_to_async(Session.objects.filter(session_key=self.session_key).update)(
                expire_date=timezone.now() - timedelta(seconds=1)
            )
            await database_sync_to_async(notify_schedule_change)(schedule_id=42, action="updated")
            self.assertEqual((await socket.receive_output())["code"], 4401)
            await socket.disconnect()
        async_to_sync(run)()

    def test_schedule_adapter_commit_and_rollback(self):
        async def run():
            socket = self.socket()
            await socket.connect()
            await socket.receive_json_from()

            def changes():
                try:
                    with transaction.atomic():
                        notify_schedule_change(schedule_id=1, action="cancelled")
                        raise RuntimeError("rolled back")
                except RuntimeError:
                    pass
                with transaction.atomic():
                    notify_schedule_change(schedule_id=2, action="created")

            await database_sync_to_async(changes)()
            event = await socket.receive_json_from()
            self.assertEqual(event["type"], "schedule.changed")
            self.assertEqual(event["data"], {"schedule_id": "2", "action": "created"})
            self.assertTrue(await socket.receive_nothing(timeout=0.05))
            await socket.disconnect()
        async_to_sync(run)()

    def test_notification_failure_does_not_undo_saved_data(self):
        with patch.object(get_channel_layer(), "group_send", new=AsyncMock(side_effect=RuntimeError("offline"))):
            with self.assertLogs("realtime.events", level="ERROR"):
                set_presence(self.user, inside=True)
            with self.assertLogs("realtime.events", level="ERROR"):
                save_message(self.user, {"content": "saved", "client_id": str(uuid4())})
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
