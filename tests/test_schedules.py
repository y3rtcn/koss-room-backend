from datetime import timedelta
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from attendance.models import OccupancyState, Visit
from common.http import ApiError
from schedules.models import CalendarLock, Participation, Schedule
from schedules.services import cancel_schedule, save_schedule
from tables.models import Table


def payload(**updates):
    start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
    return {'title': '모임', 'description': '설명', 'category': 'study',
            'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=1)).isoformat(), **updates}


class ScheduleTests(TestCase):
    def setUp(self):
        CalendarLock.objects.get_or_create(pk=1)
        self.user = get_user_model().objects.create_user(username='owner')
        self.other = get_user_model().objects.create_user(username='other')
        self.client.force_login(self.user)
        self.data = payload()

    def create(self, **updates):
        return self.client.post('/api/schedules/', {**self.data, **updates}, content_type='application/json')

    def test_crud_range_and_owner_only(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        schedule = response.json()['schedule']; pk = schedule['id']
        self.assertEqual(schedule['author']['id'], str(self.user.pk))
        self.assertEqual(schedule['recruitment']['participant_count'], 0)
        self.assertEqual(self.client.get(f'/api/schedules/{pk}/').json()['schedule'], schedule)
        query = {'start': self.data['starts_at'], 'end': self.data['ends_at']}
        self.assertEqual(len(self.client.get('/api/schedules/', query).json()['schedules']), 1)
        self.assertEqual(self.client.patch(f'/api/schedules/{pk}/', {'title': '수정'}, content_type='application/json').status_code, 200)
        self.client.force_login(self.other)
        for method, suffix in (('patch', ''), ('post', 'cancel/'), ('put', 'recruitment/')):
            body = {'capacity': 3} if method == 'put' else {}
            self.assertEqual(getattr(self.client, method)(f'/api/schedules/{pk}/{suffix}', body, content_type='application/json').status_code, 403)
        self.client.force_login(self.user)
        for changed in (True, False):
            self.assertEqual(self.client.post(f'/api/schedules/{pk}/cancel/', {}, content_type='application/json').json()['changed'], changed)
        self.assertEqual(self.client.patch(f'/api/schedules/{pk}/', {'title': '복구'}, content_type='application/json').status_code, 409)
        self.assertTrue(self.client.get('/api/schedules/', query).json()['schedules'][0]['is_cancelled'])

    def test_overlap_confirmation_create_update_and_boundaries(self):
        first = self.create().json()['schedule']
        response = self.create()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['details']['conflicts'][0]['id'], first['id'])
        second = self.create(confirm_overlap=True).json()['schedule']
        path = f"/api/schedules/{second['id']}/"
        self.assertEqual(self.client.patch(path, {'title': '겹침 유지'}, content_type='application/json').status_code, 409)
        self.assertEqual(self.client.patch(path, {'confirm_overlap': True, 'title': '확인'}, content_type='application/json').status_code, 200)
        cancel_schedule(self.user, first['id'])
        self.assertEqual(self.client.patch(path, {'title': '자기 제외'}, content_type='application/json').status_code, 200)
        end = Schedule.objects.get(pk=second['id']).ends_at
        self.assertEqual(self.create(starts_at=end.isoformat(), ends_at=(end+timedelta(hours=1)).isoformat()).status_code, 201)
        self.assertEqual(self.create(confirm_overlap='true').status_code, 400)

    def test_time_text_and_id_validation(self):
        for value in ('2026-11-04T12:00:00', '2026-02-30T12:00:00+09:00', 'not-date', None, 123, '9999-12-31T12:00:00Z', '2026-11-04T12:00:00+25:00'):
            self.assertEqual(self.create(starts_at=value).status_code, 400)
        self.assertEqual(self.create(ends_at=self.data['starts_at']).status_code, 400)
        for field, value in (('title', ''), ('title', 'a'*121), ('description', 'a'*4001), ('category', 'a'*81), ('title', '\x00'), ('description', '\ud800'), ('author_id', self.other.pk)):
            self.assertEqual(self.create(**{field:value}).status_code, 400)
        for pk in ('0', '-1', 'abc', '9'*30, '99999'):
            self.assertEqual(self.client.get(f'/api/schedules/{pk}/').status_code, 404)
        for query in ({}, {'start': self.data['starts_at'], 'end': self.data['ends_at'], 'limit': 0},
                      {'start': self.data['ends_at'], 'end': self.data['starts_at']}):
            self.assertEqual(self.client.get('/api/schedules/', query).status_code, 400)

    def test_pagination_and_anonymous(self):
        self.create(); self.create(confirm_overlap=True)
        query = {'start': self.data['starts_at'], 'end': self.data['ends_at'], 'limit': 1}
        first = self.client.get('/api/schedules/', query).json()
        second = self.client.get('/api/schedules/', {**query, 'offset': first['next_offset']}).json()
        self.assertIsNone(second['next_offset'])
        self.assertNotEqual(first['schedules'][0]['id'], second['schedules'][0]['id'])
        self.client.logout()
        self.assertEqual(self.client.get('/api/schedules/', query).status_code, 401)
        self.assertEqual(self.create().status_code, 401)

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Schedule.objects.create(author=self.user, title='bad', starts_at=timezone.now(), ends_at=timezone.now()-timedelta(hours=1))
        schedule = Schedule.objects.get(pk=self.create().json()['schedule']['id'])
        Participation.objects.create(user=self.user, schedule=schedule)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Participation.objects.create(user=self.user, schedule=schedule)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Schedule.objects.filter(pk=schedule.pk).update(recruitment_capacity=0)


class RecruitmentTests(TestCase):
    def setUp(self):
        CalendarLock.objects.get_or_create(pk=1)
        self.owner = get_user_model().objects.create_user(username='owner')
        self.other = get_user_model().objects.create_user(username='other')
        self.client.force_login(self.owner)
        self.pk = save_schedule(self.owner, payload())['id']
        self.path = f'/api/schedules/{self.pk}/'

    def config(self, capacity):
        return self.client.put(self.path+'recruitment/', {'capacity': capacity}, content_type='application/json')

    def join(self):
        return self.client.post(self.path+'participation/', {}, content_type='application/json')

    def leave(self):
        return self.client.delete(self.path+'participation/', {}, content_type='application/json')

    def test_capacity_idempotence_cancel_and_independence(self):
        state_before = OccupancyState.objects.values().get(pk=1)
        self.assertEqual(self.join().json()['error']['code'], 'recruitment_disabled')
        self.assertEqual(self.config(1).status_code, 200)
        for changed in (True, False):
            self.assertEqual(self.join().json()['changed'], changed)
        self.assertEqual(self.config(None).status_code, 409)
        self.client.force_login(self.other)
        self.assertEqual(self.join().json()['error']['code'], 'recruitment_full')
        self.assertFalse(self.leave().json()['changed'])
        self.client.force_login(self.owner)
        for changed in (True, False):
            self.assertEqual(self.leave().json()['changed'], changed)
        self.assertEqual(self.config(None).status_code, 200)
        self.assertEqual(OccupancyState.objects.values().get(pk=1), state_before)
        self.assertFalse(Visit.objects.exists())

    def test_lower_capacity_and_invalid_capacity(self):
        self.config(2); self.join()
        self.client.force_login(self.other); self.join()
        self.client.force_login(self.owner)
        self.assertEqual(self.config(1).status_code, 409)
        for value in (0, -1, True, 1.5, '2', 10001):
            self.assertEqual(self.config(value).status_code, 400)
        self.assertEqual(self.config(2).status_code, 200)
        self.assertEqual(self.client.get(self.path+'recruitment/').json()['recruitment']['participant_count'], 2)

    def test_closed_schedule_new_join_blocked_existing_retry_and_leave_allowed(self):
        self.config(2); self.join()
        cancel_schedule(self.owner, self.pk)
        self.assertFalse(self.join().json()['changed'])
        self.client.force_login(self.other)
        self.assertEqual(self.join().json()['error']['code'], 'schedule_closed')
        self.client.force_login(self.owner)
        self.assertTrue(self.leave().json()['changed'])
        self.assertEqual(self.config(3).status_code, 409)
        now = timezone.now()
        Schedule.objects.filter(pk=self.pk).update(is_cancelled=False, starts_at=now-timedelta(hours=2), ends_at=now-timedelta(hours=1))
        self.assertEqual(self.join().status_code, 409)
        self.assertEqual(self.config(3).status_code, 409)

    def test_identity_override_rejected(self):
        self.config(3)
        response = self.client.post(self.path+'participation/', {'user_id': str(self.other.pk)}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Participation.objects.exists())


class ScheduleCommitTests(TransactionTestCase):
    def setUp(self):
        CalendarLock.objects.get_or_create(pk=1)
        self.user = get_user_model().objects.create_user(username='owner')

    def test_saved_schedule_events_only_after_commit_and_rollback(self):
        with patch('realtime.events.get_channel_layer') as layer:
            layer.return_value.group_send = AsyncMock()
            with transaction.atomic():
                result = save_schedule(self.user, payload())
                layer.return_value.group_send.assert_not_called()
            event = layer.return_value.group_send.call_args.args[1]['event']
            self.assertEqual(event['data'], {'schedule_id': str(result['id']), 'action': 'created'})
            layer.return_value.group_send.reset_mock()
            with self.assertRaises(RuntimeError), transaction.atomic():
                cancel_schedule(self.user, result['id'])
                raise RuntimeError('rollback')
            layer.return_value.group_send.assert_not_called()
            self.assertFalse(Schedule.objects.get(pk=result['id']).is_cancelled)
            with self.assertRaises(RuntimeError), transaction.atomic():
                save_schedule(self.user, payload(confirm_overlap=True))
                raise RuntimeError('rollback create')
            self.assertEqual(Schedule.objects.count(), 1)
            layer.return_value.group_send.assert_not_called()
            save_schedule(self.user, {'title': 'edited'}, result['id'])
            self.assertEqual(layer.return_value.group_send.call_args.args[1]['event']['data']['action'], 'updated')
            cancel_schedule(self.user, result['id'])
            self.assertEqual(layer.return_value.group_send.call_args.args[1]['event']['data']['action'], 'cancelled')


class AMutationCSRFTests(TestCase):
    def test_all_mutation_routes_enforce_csrf_and_allow_valid_token(self):
        user = get_user_model().objects.create_user(username='member')
        CalendarLock.objects.get_or_create(pk=1)
        pk = save_schedule(user, payload())['id']
        table = Table.objects.create(name='test', capacity=1)
        client = Client(enforce_csrf_checks=True); client.force_login(user)
        token = client.get('/api/csrf/').json()['csrf_token']
        routes = [('post', '/api/schedules/', payload(confirm_overlap=True)),
                  ('patch', f'/api/schedules/{pk}/', {'title':'edit', 'confirm_overlap':True}),
                  ('put', f'/api/schedules/{pk}/recruitment/', {'capacity':2}),
                  ('post', f'/api/schedules/{pk}/participation/', {}),
                  ('delete', f'/api/schedules/{pk}/participation/', {}),
                  ('post', f'/api/schedules/{pk}/cancel/', {}),
                  ('post', f'/api/tables/{table.pk}/use/', {}),
                  ('delete', f'/api/tables/{table.pk}/use/', {})]
        for method, path, data in routes:
            with self.subTest(path=path, method=method):
                self.assertEqual(getattr(client,method)(path, data, content_type='application/json').status_code,403)
                response = getattr(client,method)(path,data,content_type='application/json',HTTP_X_CSRFTOKEN=token)
                self.assertIn(response.status_code, (200,201), response.content)
