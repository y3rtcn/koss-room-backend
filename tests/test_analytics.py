from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from analytics.services import KST, daily_statistics
from attendance.models import Visit


class AnalyticsTests(TestCase):
    def setUp(self):
        self.a = get_user_model().objects.create_user(username="a", email="a@kookmin.ac.kr")
        self.b = get_user_model().objects.create_user(username="b", email="b@kookmin.ac.kr")
        self.start = datetime(2026, 10, 31, tzinfo=KST)
        self.now = self.start + timedelta(days=1)
        self.client.force_login(self.a)

    def stats(self):
        return daily_statistics(self.start.date(), now=self.now)

    def test_time_weighted_mean_and_peak(self):
        base = self.start + timedelta(hours=10)
        Visit.objects.create(user=self.a, entered_at=base, exited_at=base + timedelta(minutes=30))
        Visit.objects.create(user=self.b, entered_at=base + timedelta(minutes=15), exited_at=base + timedelta(minutes=45))
        data = self.stats()
        self.assertEqual(data["hourly"][10]["average_count"], 1)
        self.assertEqual(data["peak_count"], 2)
        self.assertEqual(data["person_seconds"], 3600)
        self.assertEqual(data["unique_users"], 2)

    def test_equal_boundary_does_not_inflate_peak(self):
        Visit.objects.create(user=self.a, entered_at=self.start, exited_at=self.start + timedelta(hours=1))
        Visit.objects.create(user=self.b, entered_at=self.start + timedelta(hours=1), exited_at=self.start + timedelta(hours=2))
        self.assertEqual(self.stats()["peak_count"], 1)

    def test_overnight_open_visit_clipped_to_elapsed_time(self):
        Visit.objects.create(user=self.a, entered_at=self.start - timedelta(hours=2))
        self.now = self.start + timedelta(minutes=30)
        data = self.stats()
        self.assertEqual(data["person_seconds"], 1800)
        self.assertEqual(data["average_count"], 1)
        self.assertEqual(data["hourly"][0]["observed_seconds"], 1800)
        self.assertIsNone(data["hourly"][1]["average_count"])
        self.assertIsNone(Visit.objects.get().exited_at)

    def test_closed_overnight_visit_and_repeated_visits(self):
        Visit.objects.create(user=self.a, entered_at=self.start - timedelta(hours=1), exited_at=self.start + timedelta(hours=1))
        Visit.objects.create(user=self.a, entered_at=self.start + timedelta(hours=2), exited_at=self.start + timedelta(hours=3))
        data = self.stats()
        self.assertEqual(data["visit_count"], 2)
        self.assertEqual(data["unique_users"], 1)
        self.assertEqual(data["person_seconds"], 7200)

    def test_empty_day_is_zero_and_future_is_unobserved(self):
        data = self.stats()
        self.assertEqual(data["average_count"], 0)
        self.assertEqual(data["peak_count"], 0)
        self.now = self.start - timedelta(seconds=1)
        Visit.objects.create(user=self.a, entered_at=self.now)
        future = self.stats()
        self.assertEqual(future["visit_count"], 0)
        self.assertIsNone(future["average_count"])
        self.assertTrue(all(row["average_count"] is None for row in future["hourly"]))

    def test_zero_length_and_nonoverlapping_visits_are_excluded(self):
        Visit.objects.create(user=self.a, entered_at=self.start, exited_at=self.start)
        Visit.objects.create(user=self.b, entered_at=self.start - timedelta(hours=1), exited_at=self.start)
        self.assertEqual(self.stats()["visit_count"], 0)

    def test_api_dummy_and_authentication(self):
        self.assertEqual(self.client.get("/api/analytics/daily/?date=2026-10-31").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/daily/?date=bad").status_code, 400)
        summary = self.client.get("/api/analytics/summary/").json()
        self.assertTrue(summary["is_dummy"])
        self.assertFalse(summary["uses_ai"])
        self.client.logout()
        self.assertEqual(self.client.get("/api/analytics/daily/").status_code, 401)
        self.assertEqual(self.client.get("/api/analytics/summary/").status_code, 401)
