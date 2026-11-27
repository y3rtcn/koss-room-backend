from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from analytics.recommendations import space_recommendations
from analytics.services import KST
from schedules.models import Participation, Schedule
from spaces.models import Space


class RecommendationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analysis", email="analysis@kookmin.ac.kr",
        )
        self.space = Space.objects.create(name="분석 공간", capacity=10)
        self.url = f"/api/analytics/recommendations/?date=2030-01-02&space_id={self.space.pk}"

    def login(self):
        self.client.force_login(self.user, backend="allauth.account.auth_backends.AuthenticationBackend")

    def schedule(self, start, end, users, cancelled=False):
        row = Schedule.objects.create(
            title="분석", purpose="테스트", creator=self.user, space=self.space,
            starts_at=datetime(2030, 1, 2, start, tzinfo=KST),
            ends_at=datetime(2030, 1, 2, end, tzinfo=KST),
            expected_count=8, is_cancelled=cancelled,
        )
        for user in users:
            Participation.objects.create(schedule=row, user=user)
        return row

    def test_authentication_and_method(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.login()
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_empty_data_is_unknown_not_empty_room(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(len(result["recommendations"]), 24)
        self.assertEqual(result["space_ids"], [self.space.pk])
        self.assertIn("no-store", response.headers["Cache-Control"])
        for slot in result["recommendations"]:
            self.assertIsNone(slot["estimated_count"])
            self.assertFalse(slot["recommended"])
            self.assertEqual(slot["history"]["sample_days"], 0)

    def test_real_participants_deduplicated_and_cancelled_ignored(self):
        other = get_user_model().objects.create_user(username="other", email="other@kookmin.ac.kr")
        self.schedule(10, 11, [self.user])
        self.schedule(10, 12, [self.user, other])
        self.schedule(12, 13, [other], cancelled=True)
        with self.assertNumQueries(2):
            result = space_recommendations(self.space, datetime(2030, 1, 2).date())
        slots = result["recommendations"]
        self.assertEqual(slots[10]["reservation_count"], 2)
        self.assertEqual(slots[11]["reservation_count"], 2)
        self.assertEqual(slots[12]["reservation_count"], 0)
        self.assertEqual(slots[10]["congestion_ratio"], 0.2)
        self.assertFalse(slots[10]["recommended"])

    def test_invalid_inputs_and_inactive_space(self):
        self.login()
        for raw in ("", "-1", "0", "abc", "9" * 100, "１"):
            self.assertEqual(self.client.get("/api/analytics/recommendations/", {"space_id": raw}).status_code, 400)
        self.assertEqual(self.client.get(self.url.replace("2030-01-02", "bad")).status_code, 400)
        self.space.is_active = False
        self.space.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
