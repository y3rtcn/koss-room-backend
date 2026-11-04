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

# Create your tests here.
