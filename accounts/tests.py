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

class NicknameUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="nickname-member",
            email="nickname-member@kookmin.ac.kr",
            nickname="기존 닉네임",
        )
        self.client.force_login(self.user)

    def update_nickname(self, nickname):
        return self.client.patch(
            "/api/accounts/me/",
            data={"nickname": nickname},
            content_type="application/json",
        )

    def test_updates_and_saves_nickname(self):
        response = self.update_nickname("  파이썬 스터디원  ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nickname"], "파이썬 스터디원")
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "파이썬 스터디원")

    def test_rejects_invalid_nicknames(self):
        for nickname in ("   ", "가" * 31, "줄\n바꿈", 123):
            with self.subTest(nickname=nickname):
                response = self.update_nickname(nickname)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "invalid_nickname")

        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "기존 닉네임")

    def test_requires_login(self):
        self.client.logout()

        response = self.update_nickname("새 닉네임")

        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "기존 닉네임")
