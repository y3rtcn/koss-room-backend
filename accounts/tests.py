from django.contrib.auth import get_user_model
from django.test import TestCase


class AccountMeTests(TestCase):
    def test_login_required(self):
        response = self.client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["code"],
            "authentication_required",
        )

    def test_returns_current_user(self):
        user = get_user_model().objects.create_user(
            username="test-member",
            email="test-member@kookmin.ac.kr",
            nickname="테스트회원",
        )
        self.client.force_login(user)

        response = self.client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": str(user.pk),
            "email": "test-member@kookmin.ac.kr",
            "nickname": "테스트회원",
        })

# Create your tests here.
