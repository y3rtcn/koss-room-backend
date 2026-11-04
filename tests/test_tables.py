from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from attendance.models import OccupancyState, Visit
from tables.models import Table, TableUse


class TableTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='member')
        self.other = get_user_model().objects.create_user(username='other')
        self.table = Table.objects.create(name='table 1', capacity=1)
        self.second = Table.objects.create(name='table 2', capacity=2)
        self.client.force_login(self.user)

    def use(self, table=None, *, start=True, data=None):
        return getattr(self.client, 'post' if start else 'delete')(
            f'/api/tables/{(table or self.table).pk}/use/', data or {}, content_type='application/json')

    def test_retry_capacity_movement_and_independent_attendance(self):
        state = OccupancyState.objects.values().get(pk=1)
        for changed in (True, False):
            self.assertEqual(self.use().json()['changed'], changed)
        self.assertEqual(TableUse.objects.count(), 1)
        self.assertEqual(self.use(self.second).json()['error']['code'], 'already_using_table')
        self.assertFalse(self.use(self.second, start=False).json()['changed'])
        self.assertTrue(self.client.get('/api/tables/').json()['tables'][0]['is_using'])
        self.client.force_login(self.other)
        self.assertEqual(self.use().json()['error']['code'], 'table_full')
        self.assertFalse(self.use(start=False).json()['changed'])
        self.client.force_login(self.user)
        for changed in (True, False):
            self.assertEqual(self.use(start=False).json()['changed'], changed)
        self.assertEqual(self.use(self.second).status_code, 200)
        self.assertEqual(TableUse.objects.count(), 2)
        self.assertFalse(Visit.objects.exists())
        self.assertEqual(OccupancyState.objects.values().get(pk=1), state)

    def test_cannot_choose_another_user_and_not_found_auth(self):
        self.use()
        self.client.force_login(self.other)
        for start in (True,False):
            self.assertEqual(self.use(start=start, data={'user_id': str(self.user.pk)}).status_code, 400)
        self.assertTrue(TableUse.objects.filter(user=self.user, ended_at__isnull=True).exists())
        for value in ('9999', 'abc', '9'*30):
            self.assertEqual(self.client.post(f'/api/tables/{value}/use/', {}, content_type='application/json').status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get('/api/tables/').status_code, 401)
        self.assertEqual(self.use().status_code, 401)

    def test_database_constraints(self):
        self.use()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TableUse.objects.create(table=self.second, user=self.user, started_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Table.objects.create(name='zero', capacity=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TableUse.objects.create(table=self.second,user=self.other,started_at=timezone.now(),ended_at=timezone.now()-timedelta(hours=1))
