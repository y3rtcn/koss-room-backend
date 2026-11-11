from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Space

from datetime import timedelta

from django.utils import timezone

from schedules.models import Schedule

class SpaceListTests(TestCase):
    def test_login_required(self):
        response = self.client.get("/api/spaces/")
        self.assertEqual(response.status_code, 401)

    def test_returns_only_active_spaces(self):
        user = get_user_model().objects.create_user(
            username="space-member",
            email="space-member@kookmin.ac.kr",
        )
        self.client.force_login(user)

        active = Space.objects.create(name="테이블 A", capacity=4)
        Space.objects.create(
            name="사용 중지 테이블",
            capacity=2,
            is_active=False,
        )

        response = self.client.get("/api/spaces/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "spaces": [
                {
                    "id": active.pk,
                    "name": "테이블 A",
                    "capacity": 4,
                }
            ]
        })

class SpaceCreateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="space-admin",
            email="space-admin@kookmin.ac.kr",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def post(self, data):
        return self.client.post(
            "/api/spaces/create/",
            data=data,
            content_type="application/json",
        )

    def test_admin_can_create_space(self):
        response = self.post({"name": "테이블 B", "capacity": 6})

        self.assertEqual(response.status_code, 201)
        space = Space.objects.get(name="테이블 B")
        self.assertEqual(space.capacity, 6)

    def test_regular_member_cannot_create_space(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])

        response = self.post({"name": "테이블 B", "capacity": 6})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Space.objects.exists())

    def test_duplicate_name_is_rejected(self):
        Space.objects.create(name="테이블 B", capacity=4)

        response = self.post({"name": "테이블 B", "capacity": 6})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Space.objects.count(), 1)

    def test_invalid_input_is_rejected(self):
        for data in [
            {"name": "", "capacity": 4},
            {"name": "테이블 B", "capacity": 0},
            {"name": "테이블 B", "capacity": True},
            {"name": "테이블 B", "capacity": "4"},
        ]:
            with self.subTest(data=data):
                response = self.post(data)
                self.assertEqual(response.status_code, 400)

        self.assertFalse(Space.objects.exists())

class SpaceUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="capacity-admin",
            email="capacity-admin@kookmin.ac.kr",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.space = Space.objects.create(name="테이블 C", capacity=4)

    def patch(self, data, space_id=None):
        if space_id is None:
            space_id = self.space.pk
        return self.client.patch(
            f"/api/spaces/{space_id}/",
            data=data,
            content_type="application/json",
        )

    def test_admin_can_update_capacity(self):
        response = self.patch({"capacity": 6})

        self.assertEqual(response.status_code, 200)
        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 6)

    def test_regular_member_cannot_update_capacity(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])

        response = self.patch({"capacity": 6})

        self.assertEqual(response.status_code, 403)
        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 4)

    def test_missing_space_returns_404(self):
        missing_id = self.space.pk + 1
        response = self.patch({"capacity": 6}, space_id=missing_id)

        self.assertEqual(response.status_code, 404)

    def test_invalid_capacity_is_rejected(self):
        for capacity in [0, -1, True, "4", None, 32768]:
            with self.subTest(capacity=capacity):
                response = self.patch({"capacity": capacity})
                self.assertEqual(response.status_code, 400)

        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 4)

    def test_login_required(self):
        self.client.logout()

        response = self.patch({"capacity": 6})

        self.assertEqual(response.status_code, 401)
    def create_reservation(self, *, starts_at, ends_at, cancelled=False):
        return Schedule.objects.create(
            title="테이블 예약",
            creator=self.user,
            space=self.space,
            starts_at=starts_at,
            ends_at=ends_at,
            expected_count=3,
            purpose="스터디",
            is_cancelled=cancelled,
        )

    def test_cannot_reduce_capacity_below_upcoming_reservation(self):
        now = timezone.now()
        self.create_reservation(
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
        )

        response = self.patch({"capacity": 2})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "space_capacity_conflict")
        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 4)

    def test_can_reduce_capacity_to_reserved_count(self):
        now = timezone.now()
        self.create_reservation(
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )

        response = self.patch({"capacity": 3})

        self.assertEqual(response.status_code, 200)
        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 3)

    def test_ended_and_cancelled_reservations_do_not_block_reduction(self):
        now = timezone.now()
        self.create_reservation(
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
        )
        self.create_reservation(
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            cancelled=True,
        )

        response = self.patch({"capacity": 2})

        self.assertEqual(response.status_code, 200)
        self.space.refresh_from_db()
        self.assertEqual(self.space.capacity, 2)