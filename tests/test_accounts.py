import os
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, TransactionTestCase, override_settings

from accounts.models import Profile
from accounts.nicknames import display_nickname
from attendance.models import OccupancyState, Visit
from chat.models import Message
from config.asgi import application
from schedules.models import CalendarLock, Schedule
from tables.models import Table


class AuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='private-id', password='test-only-password')
        Profile.objects.create(user=self.user, nickname='프로필 별명')
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get('/api/csrf/').json()['csrf_token']

    def login(self, **changes):
        return self.client.post('/api/auth/login/', {'username': 'private-id', 'password': 'test-only-password', **changes},
                                content_type='application/json', HTTP_X_CSRFTOKEN=self.token)

    def test_csrf_rotation_real_login_b_chat_and_logout(self):
        self.assertEqual(self.client.post('/api/auth/login/', {}).status_code, 403)
        old_cookie = self.client.cookies['csrftoken'].value
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user'], {'id': str(self.user.pk), 'nickname': '프로필 별명'})
        self.assertNotEqual(self.client.cookies['csrftoken'].value, old_cookie)
        self.assertEqual(self.client.post('/api/attendance/check-in/', HTTP_X_CSRFTOKEN=self.token).status_code, 403)
        self.token = response.json()['csrf_token']
        self.assertEqual(self.client.get('/api/auth/me/').json()['user'], response.json()['user'])
        self.assertEqual(self.client.post('/api/attendance/check-in/', HTTP_X_CSRFTOKEN=self.token).status_code, 200)
        chat = self.client.post('/api/chat/messages/', {'content': 'hello', 'client_id': str(uuid4())},
                                content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(chat.json()['message']['nickname'], '프로필 별명')
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=self.token).status_code, 200)
        for path in ('/api/auth/me/', '/api/attendance/me/', '/api/chat/messages/', '/api/analytics/daily/', '/api/tables/'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/api/attendance/check-out/', HTTP_X_CSRFTOKEN=self.token).status_code, 401)
        self.assertTrue(Visit.objects.filter(exited_at__isnull=True).exists())

    def test_invalid_inactive_and_missing_password(self):
        for password in ('wrong', '', None, '\ud800'):
            self.assertEqual(self.login(password=password).status_code, 401)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/login/').status_code, 405)

    def test_json_validation_and_no_identity_override(self):
        self.assertEqual(self.login(user_id='other').status_code, 400)
        for body, status in (('[]', 400), ('{', 400), ('{"username":"' + 'a' * 17000 + '"}', 413)):
            response = self.client.post('/api/auth/login/', body, content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
            self.assertEqual(response.status_code, status)
        self.assertEqual(self.client.post('/api/auth/login/', {}, HTTP_X_CSRFTOKEN=self.token).status_code, 415)

    def test_nickname_no_identifier_fallback_and_snapshot(self):
        Profile.objects.filter(user=self.user).delete()
        for field in ('username', 'email', 'password'):
            with override_settings(ROOM_NICKNAME_FIELD=field):
                self.assertEqual(display_nickname(get_user_model().objects.get(pk=self.user.pk)), '동아리원')
        self.login()
        token = self.client.get('/api/csrf/').json()['csrf_token']
        profile = Profile.objects.create(user=self.user, nickname='처음')
        self.client.post('/api/chat/messages/', {'content': 'snapshot', 'client_id': str(uuid4())},
                         content_type='application/json', HTTP_X_CSRFTOKEN=token)
        profile.nickname = '나중'
        profile.save()
        self.assertEqual(Message.objects.get().nickname, '처음')


class LoginSocketTests(TransactionTestCase):
    def setUp(self):
        OccupancyState.objects.get_or_create(pk=1)
        CalendarLock.objects.get_or_create(pk=1)
        self.user = get_user_model().objects.create_user(username='socket-demo', password='test-only-password')
        Profile.objects.create(user=self.user, nickname='소켓 별명')
        self.client = Client(enforce_csrf_checks=True)
        token = self.client.get('/api/csrf/').json()['csrf_token']
        response = self.client.post('/api/auth/login/', {'username': 'socket-demo', 'password': 'test-only-password'},
                                    content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.token = response.json()['csrf_token']
        self.cookie = f"sessionid={self.client.cookies['sessionid'].value}".encode()

    def test_login_api_cookie_socket_chat_and_logout(self):
        async def run():
            socket = WebsocketCommunicator(application, '/ws/room/', headers=[
                (b'origin', b'http://localhost:8000'), (b'cookie', self.cookie)])
            self.assertTrue((await socket.connect())[0])
            await socket.receive_json_from()
            response = await database_sync_to_async(self.client.post)('/api/attendance/check-in/', HTTP_X_CSRFTOKEN=self.token)
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await socket.receive_json_from())['type'], 'attendance.updated')
            await socket.send_json_to({'type': 'chat.send', 'content': 'logged in', 'client_id': str(uuid4())})
            replies = [await socket.receive_json_from(), await socket.receive_json_from()]
            for reply in replies:
                self.assertEqual(reply['data']['message']['nickname'], '소켓 별명')
            from tests.test_schedules import payload
            created = await database_sync_to_async(self.client.post)('/api/schedules/', payload(),
                content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
            self.assertEqual(created.status_code, 201)
            event = await socket.receive_json_from()
            self.assertEqual(event['type'], 'schedule.changed')
            self.assertEqual(event['data'], {'schedule_id': str(created.json()['schedule']['id']), 'action': 'created'})
            response = await database_sync_to_async(self.client.post)('/api/auth/logout/', HTTP_X_CSRFTOKEN=self.token)
            self.assertEqual(response.status_code, 200)
            await socket.send_json_to({'type': 'ping'})
            self.assertEqual((await socket.receive_output())['code'], 4401)
            await socket.disconnect()
            reconnect = WebsocketCommunicator(application, '/ws/room/', headers=[
                (b'origin', b'http://localhost:8000'), (b'cookie', self.cookie)])
            self.assertFalse((await reconnect.connect())[0])
            await reconnect.disconnect()
        async_to_sync(run)()
        self.assertEqual(self.client.get('/api/attendance/me/').status_code, 401)


class DemoSeedTests(TestCase):
    def seed(self):
        with patch.dict(os.environ, {'KOSS_DEMO_PASSWORD': 'test-only-demo-password'}):
            call_command('seed_demo', stdout=StringIO())

    def test_repeated_seed_preserves_password_and_user_changes(self):
        CalendarLock.objects.get_or_create(pk=1)
        self.seed()
        self.assertEqual(get_user_model().objects.count(), 2)
        self.assertEqual(Profile.objects.values('nickname').distinct().count(), 2)
        user = get_user_model().objects.get(username='demo-room-a')
        password = user.password
        user.username = 'renamed-demo'
        user.save()
        profile = user.room_profile
        profile.nickname = '직접 수정'
        profile.save()
        schedule = Schedule.objects.get()
        schedule.title = '변경한 일정'
        schedule.save()
        table = Table.objects.first()
        table.name = '변경한 테이블'
        table.save()
        with patch.dict(os.environ, {}, clear=True), patch('getpass.getpass', side_effect=AssertionError('unexpected prompt')):
            call_command('seed_demo', stdout=StringIO())
        user.refresh_from_db(); schedule.refresh_from_db(); table.refresh_from_db(); profile.refresh_from_db()
        self.assertEqual(user.password, password)
        self.assertEqual(profile.nickname, '직접 수정')
        self.assertEqual(schedule.title, '변경한 일정')
        self.assertEqual(table.name, '변경한 테이블')
        self.assertEqual((get_user_model().objects.count(), Table.objects.count(), Schedule.objects.count()), (2, 3, 1))
        self.assertFalse(user.is_staff)
        self.assertEqual(schedule.participations.count(), 0)

    def test_existing_username_collision_rolls_back(self):
        get_user_model().objects.create_user(username='demo-room-b')
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(Table.objects.exists())
