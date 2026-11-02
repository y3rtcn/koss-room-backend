from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from attendance.models import OccupancyState, Visit
from attendance.services import set_presence


class AttendanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="member")
        self.client.force_login(self.user)

    def test_full_attendance_flow_and_repeated_buttons(self):
        self.assertFalse(self.client.get("/api/attendance/me/").json()["is_inside"])
        first = self.client.post("/api/attendance/check-in/").json()
        again = self.client.post("/api/attendance/check-in/").json()
        self.assertEqual(first["current_count"], 1)
        self.assertTrue(first["changed"])
        self.assertFalse(again["changed"])
        self.assertEqual(first["revision"], again["revision"])
        self.assertEqual(Visit.objects.count(), 1)
        other = get_user_model().objects.create_user(username="other")
        set_presence(other, inside=True)
        out = self.client.post("/api/attendance/check-out/").json()
        repeated = self.client.post("/api/attendance/check-out/").json()
        self.assertEqual(out["current_count"], 1)
        self.assertFalse(out["is_inside"])
        self.assertFalse(repeated["changed"])
        self.assertIsNotNone(Visit.objects.get(user=self.user).exited_at)

    def test_body_cannot_choose_another_user(self):
        other = get_user_model().objects.create_user(username="other")
        self.client.post("/api/attendance/check-in/", {"user_id": other.pk})
        self.assertEqual(Visit.objects.get().user_id, self.user.pk)

    def test_database_rejects_duplicate_open_visit(self):
        Visit.objects.create(user=self.user, entered_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Visit.objects.create(user=self.user, entered_at=timezone.now())

    def test_database_rejects_reversed_interval(self):
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Visit.objects.create(user=self.user, entered_at=now, exited_at=now - timedelta(seconds=1))

    def test_notification_only_after_commit_and_only_on_change(self):
        with patch("realtime.events.get_channel_layer") as layer:
            from unittest.mock import AsyncMock
            layer.return_value.group_send = AsyncMock()
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                set_presence(self.user, inside=True)
                set_presence(self.user, inside=True)
                layer.return_value.group_send.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            layer.return_value.group_send.assert_called_once()

    def test_rollback_does_not_publish(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    set_presence(self.user, inside=True)
                    raise RuntimeError("rollback")
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])
        self.assertFalse(Visit.objects.exists())

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/api/attendance/check-in/").status_code, 403)
        token = client.get("/api/csrf/").json()["csrf_token"]
        self.assertEqual(client.post("/api/attendance/check-in/", HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_authentication_and_methods(self):
        self.assertEqual(self.client.get("/api/attendance/check-in/").status_code, 405)
        self.client.logout()
        for path in ("me/", "occupancy/", "check-in/", "check-out/"):
            self.assertEqual(self.client.get("/api/attendance/" + path).status_code, 401)


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL")
class AttendanceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        OccupancyState.objects.get_or_create(pk=1)
        self.users = [get_user_model().objects.create_user(username=f"member-{i}") for i in range(4)]

    def parallel(self, users, inside):
        barrier = Barrier(len(users))

        def worker(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return set_presence(user, inside=inside)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(users)) as pool:
            return list(pool.map(worker, users))

    def test_same_user_concurrent_check_in_and_out(self):
        results = self.parallel([self.users[0]] * 4, True)
        self.assertEqual(sum(row["changed"] for row in results), 1)
        self.assertEqual(Visit.objects.filter(exited_at__isnull=True).count(), 1)
        results = self.parallel([self.users[0]] * 4, False)
        self.assertEqual(sum(row["changed"] for row in results), 1)
        self.assertFalse(Visit.objects.filter(exited_at__isnull=True).exists())

    def test_different_users_get_consistent_count_and_revision(self):
        results = self.parallel(self.users, True)
        self.assertEqual(sorted(row["current_count"] for row in results), [1, 2, 3, 4])
        self.assertEqual(sorted(row["revision"] for row in results), [1, 2, 3, 4])
        results = self.parallel(self.users, False)
        self.assertEqual(sorted(row["current_count"] for row in results), [0, 1, 2, 3])
