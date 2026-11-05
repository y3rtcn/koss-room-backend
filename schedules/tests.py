from django.contrib.auth import get_user_model
from django.test import TestCase

from spaces.models import Space
from .models import Schedule


class ScheduleCreateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="schedule-member",
            email="schedule-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        self.space = Space.objects.create(name="일정 테스트 공간", capacity=4)
        self.payload = {
            "title": "스터디",
            "space_id": self.space.pk,
            "starts_at": "2026-11-10T14:00:00+09:00",
            "ends_at": "2026-11-10T15:00:00+09:00",
            "expected_count": 3,
            "purpose": "공부",
        }

    def post(self, **changes):
        data = {**self.payload, **changes}
        return self.client.post(
            "/api/schedules/create/",
            data=data,
            content_type="application/json",
        )

    def test_create_schedule(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        schedule = Schedule.objects.get()
        self.assertEqual(schedule.creator, self.user)
        self.assertEqual(schedule.space, self.space)
        self.assertEqual(schedule.expected_count, 3)

    def test_overlap_requires_confirmation(self):
        self.post()
        response = self.post(title="겹치는 일정")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "schedule_overlap")
        self.assertEqual(len(response.json()["conflicts"]), 1)
        self.assertEqual(Schedule.objects.count(), 1)

    def test_confirmed_overlap_can_be_created(self):
        self.post()
        response = self.post(
            title="확인한 일정",
            confirm_overlap=True,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Schedule.objects.count(), 2)

    def test_adjacent_times_do_not_overlap(self):
        self.post()
        response = self.post(
            starts_at="2026-11-10T15:00:00+09:00",
            ends_at="2026-11-10T16:00:00+09:00",
        )

        self.assertEqual(response.status_code, 201)

    def test_capacity_exceeded(self):
        response = self.post(expected_count=5)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Schedule.objects.exists())

    def test_invalid_interval(self):
        response = self.post(
            ends_at="2026-11-10T13:00:00+09:00",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Schedule.objects.exists())

    def test_inactive_space_is_rejected(self):
        self.space.is_active = False
        self.space.save(update_fields=["is_active"])

        response = self.post()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Schedule.objects.exists())

    def test_login_required(self):
        self.client.logout()
        response = self.post()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Schedule.objects.exists())

class ScheduleDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="detail-member",
            email="detail-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        space = Space.objects.create(name="상세 조회 공간", capacity=4)

        from django.utils.dateparse import parse_datetime

        self.schedule = Schedule.objects.create(
            title="상세 조회 스터디",
            creator=self.user,
            space=space,
            starts_at=parse_datetime("2026-11-10T14:00:00+09:00"),
            ends_at=parse_datetime("2026-11-10T15:00:00+09:00"),
            expected_count=3,
            purpose="공부",
        )
        self.url = f"/api/schedules/{self.schedule.pk}/"

    def test_returns_schedule(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["schedule"]
        self.assertEqual(data["id"], self.schedule.pk)
        self.assertEqual(data["title"], "상세 조회 스터디")
        self.assertEqual(data["creator_id"], str(self.user.pk))
        self.assertEqual(data["space_id"], self.schedule.space_id)

    def test_cancelled_schedule_can_be_viewed(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["schedule"]["is_cancelled"])

    def test_missing_schedule_returns_404(self):
        missing_id = self.schedule.pk + 1
        response = self.client.get(f"/api/schedules/{missing_id}/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["code"],
            "schedule_not_found",
        )

    def test_login_required(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)