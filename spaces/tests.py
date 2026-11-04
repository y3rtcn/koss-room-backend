from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Space


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
# Create your tests here.
