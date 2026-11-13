from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings

from attendance.models import OccupancyState
from chat.models import Message
from chat.services import KST, save_message


class ChatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="private-login-id", first_name="닉네임", email="chat-member@kookmin.ac.kr")
        self.client.force_login(self.user)
        self.payload = {"content": "안녕하세요 <script>text</script>", "client_id": str(uuid4())}

    def post(self, data):
        return self.client.post("/api/chat/messages/", data, content_type="application/json")

    def test_persistence_retry_and_conflicting_retry(self):
        self.assertEqual(self.post(self.payload).status_code, 201)
        self.assertEqual(self.post(self.payload).status_code, 200)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(self.post({**self.payload, "content": "different"}).status_code, 409)
        self.assertEqual(self.client.get("/api/chat/messages/").json()["messages"][0]["content"], self.payload["content"])

    def test_nickname_snapshot_and_no_login_identifier_fallback(self):
        self.assertEqual(self.post(self.payload).json()["message"]["nickname"], "동아리원")
        with override_settings(ROOM_NICKNAME_FIELD="first_name"):
            response = self.post({**self.payload, "client_id": str(uuid4())})
        self.assertEqual(response.json()["message"]["nickname"], "닉네임")
        self.user.first_name = "변경됨"
        self.user.save()
        self.assertEqual(Message.objects.last().nickname, "닉네임")

    def test_validation(self):
        for content in ("", "  ", "x" * 501, 12, None, [], "\x00", "\ud800"):
            with self.subTest(content=content):
                self.assertEqual(self.post({**self.payload, "content": content}).status_code, 400)
        self.assertEqual(self.post({**self.payload, "client_id": "bad"}).status_code, 400)
        self.assertEqual(self.post({**self.payload, "content": "한" * 500}).status_code, 201)
        self.assertEqual(self.post([]).status_code, 400)
        self.assertEqual(self.client.post("/api/chat/messages/", "{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/chat/messages/", self.payload).status_code, 415)

    def test_per_user_idempotency_key(self):
        self.post(self.payload)
        self.client.force_login(get_user_model().objects.create_user(username="other", email="other@kookmin.ac.kr"))
        self.assertEqual(self.post(self.payload).status_code, 201)

    def test_korean_midnight_and_bidirectional_pagination(self):
        start = datetime(2026, 10, 31, tzinfo=KST)
        messages = [Message.objects.create(user=self.user, nickname="동아리원", content=str(i), client_id=uuid4(),
                                          created_at=start + timedelta(hours=i)) for i in (-1, 0, 1, 2, 24)]
        response = self.client.get("/api/chat/messages/?date=2026-10-31&limit=2").json()
        self.assertEqual([m["content"] for m in response["messages"]], ["1", "2"])
        self.assertTrue(response["has_more"])
        older = self.client.get(f'/api/chat/messages/?date=2026-10-31&before_id={response["next_before_id"]}').json()
        self.assertEqual([m["content"] for m in older["messages"]], ["0"])
        newer = self.client.get(f"/api/chat/messages/?date=2026-10-31&after_id={messages[1].pk}&limit=1").json()
        self.assertEqual([m["content"] for m in newer["messages"]], ["1"])
        self.assertTrue(newer["has_more"])

    def test_invalid_queries_and_anonymous(self):
        for query in ("limit=0", "limit=101", "limit=x", "before_id=-1", "before_id=1&after_id=2", "date=2026-02-30", "date=20261031", "date=0001-01-01", "date=9999-12-31"):
            self.assertEqual(self.client.get("/api/chat/messages/?" + query).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get("/api/chat/messages/").status_code, 401)
        self.assertEqual(self.post(self.payload).status_code, 401)


@skipUnless(connection.vendor == "postgresql", "Concurrent writes require PostgreSQL")
class ChatConcurrencyTests(TransactionTestCase):
    def setUp(self):
        OccupancyState.objects.get_or_create(pk=1)

    def test_simultaneous_retries_save_one_message(self):
        user = get_user_model().objects.create_user(username="member", email="member@kookmin.ac.kr")
        payload = {"content": "one message", "client_id": str(uuid4())}
        barrier = Barrier(4)

        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return save_message(user, payload)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(worker, range(4)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(Message.objects.count(), 1)
