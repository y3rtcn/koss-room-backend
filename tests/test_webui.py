from django.test import SimpleTestCase


class WebUITests(SimpleTestCase):
    def test_home_serves_ui_without_requiring_session(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content).decode()
        self.assertIn('KOSS ROOM', body)
        self.assertIn('/ui/app.js', body)
        self.assertIn('id="login-form"', body)
        self.assertIn('id="schedule-form"', body)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_only_public_assets_are_served(self):
        for name, content_type in [('app.js', 'text/javascript'), ('app.css', 'text/css')]:
            with self.subTest(name=name):
                response = self.client.get('/ui/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertIn(content_type, response.headers['Content-Type'])
                self.assertTrue(b''.join(response.streaming_content))
        for path in ['/ui/settings.py', '/ui/index.html', '/ui/.env', '/ui/../db.sqlite3']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_ui_is_read_only_and_unknown_paths_stay_404(self):
        self.assertEqual(self.client.post('/').status_code, 405)
        self.assertEqual(self.client.post('/ui/app.js').status_code, 405)
        self.assertEqual(self.client.get('/nonexistent/').status_code, 404)
