from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.database_url import parse_database_url


class DatabaseUrlTests(SimpleTestCase):
    def test_neon_direct_url(self):
        config = parse_database_url(
            "postgresql://koss_owner:p%40ss%2Fword@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "neondb")
        self.assertEqual(config["USER"], "koss_owner")
        self.assertEqual(config["PASSWORD"], "p@ss/word")
        self.assertEqual(config["HOST"], "ep-cool-name-123456.ap-southeast-1.aws.neon.tech")
        self.assertEqual(config["PORT"], "5432")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require", "channel_binding": "require"})
        self.assertNotIn("DISABLE_SERVER_SIDE_CURSORS", config)

    def test_defaults_to_sslmode_require(self):
        config = parse_database_url("postgres://u:p@db.example.com:6543/app")
        self.assertEqual(config["PORT"], "6543")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})

    def test_pooler_host_disables_server_side_cursors(self):
        config = parse_database_url(
            "postgresql://u:p@ep-cool-name-123456-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
        )
        self.assertTrue(config["DISABLE_SERVER_SIDE_CURSORS"])

    def test_rejects_non_postgres_or_incomplete_url(self):
        for url in ("mysql://u:p@h/db", "postgresql://u:p@h", "postgresql:///db"):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                parse_database_url(url)
