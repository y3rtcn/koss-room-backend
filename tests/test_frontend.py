import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings


class FrontendServingTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dist = Path(self.tmp.name)
        override = override_settings(FRONTEND_DIST_DIR=self.dist)
        override.enable()
        self.addCleanup(override.disable)

    def build(self):
        (self.dist / "assets").mkdir()
        (self.dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
        (self.dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
        (self.dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    def test_index_served_at_root_without_long_cache(self):
        self.build()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"id=root", b"".join(response.streaming_content))
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(self.client.head("/").status_code, 200)

    def test_root_without_build_is_clear_404(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("frontend_dist/index.html", response.content.decode())

    def test_assets_served_with_immutable_cache(self):
        self.build()
        response = self.client.get("/assets/index-abc123.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("immutable", response["Cache-Control"])
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)

    def test_root_level_static_files(self):
        self.build()
        self.assertEqual(self.client.get("/favicon.svg").status_code, 200)
        self.assertEqual(self.client.get("/missing.png").status_code, 404)
        self.assertEqual(self.client.get("/index.html").status_code, 404)

    def test_no_path_traversal_or_write_methods(self):
        self.build()
        for url in ("/assets/../index.html", "/assets/%2e%2e/index.html", "/assets/..%2findex.html"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, (400, 404))
                self.assertNotIn("id=root", response.content.decode() if not response.streaming else "")
        self.assertEqual(self.client.post("/").status_code, 405)
        self.assertEqual(self.client.post("/assets/index-abc123.js").status_code, 405)

    def test_existing_routes_are_not_swallowed(self):
        self.build()
        self.assertEqual(self.client.get("/api/csrf/").status_code, 200)
        self.assertEqual(self.client.get("/api/attendance/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/does-not-exist/").status_code, 404)
        self.assertEqual(self.client.get("/schedule").status_code, 404)


class RedirectAndTemplateSettingsTests(SimpleTestCase):
    def test_login_and_logout_return_to_frontend_home(self):
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "/")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "/")

    def test_project_templates_dir_is_searched_first(self):
        self.assertEqual(settings.TEMPLATES[0]["DIRS"], [settings.BASE_DIR / "templates"])


class LogoutRedirectTests(TestCase):
    def test_logout_post_returns_to_frontend_home(self):
        user = get_user_model().objects.create_user(username="logout", email="logout@kookmin.ac.kr")
        self.client.force_login(user, backend="allauth.account.auth_backends.AuthenticationBackend")
        response = self.client.post("/accounts/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 401)
