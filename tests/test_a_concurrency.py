from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from common.http import ApiError
from schedules.models import CalendarLock, Participation, Schedule
from schedules.services import cancel_schedule, configure_recruitment, participate, save_schedule
from tables.models import Table, TableUse
from tables.services import set_use
from tests.test_schedules import payload


@skipUnless(connection.vendor == 'postgresql', 'A row-lock concurrency requires PostgreSQL')
class AConcurrencyTests(TransactionTestCase):
    def setUp(self):
        CalendarLock.objects.get_or_create(pk=1)
        self.users = [get_user_model().objects.create_user(username=f'member-{i}') for i in range(4)]
        self.table = Table.objects.create(name='small table', capacity=2)
        self.other_table = Table.objects.create(name='second table', capacity=2)
        self.schedule = save_schedule(self.users[0], payload())['id']
        configure_recruitment(self.users[0], self.schedule, {'capacity': 2})

    def parallel(self, jobs):
        barrier = Barrier(len(jobs))
        def worker(job):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return job()
                except ApiError as exc:
                    return exc.code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            return list(pool.map(worker, jobs))

    def test_table_last_seats_and_same_user_retries(self):
        results = self.parallel([lambda user=u: set_use(user, self.table.pk, start=True) for u in self.users])
        self.assertEqual(results.count('table_full'), 2)
        self.assertEqual(TableUse.objects.filter(ended_at__isnull=True).count(), 2)
        occupant = TableUse.objects.filter(ended_at__isnull=True).first().user
        results = self.parallel([lambda: set_use(occupant, self.table.pk, start=False)]*4)
        self.assertEqual(sum(r['changed'] for r in results), 1)
        results = self.parallel([lambda: set_use(occupant, self.table.pk, start=True)]*4)
        self.assertEqual(sum(r['changed'] for r in results), 1)
        self.assertEqual(TableUse.objects.filter(user=occupant, ended_at__isnull=True).count(), 1)

    def test_same_user_competing_tables(self):
        results = self.parallel([lambda table=t: set_use(self.users[0], table.pk, start=True)
                                 for t in (self.table, self.other_table)])
        self.assertEqual(results.count('already_using_table'), 1)
        self.assertEqual(TableUse.objects.filter(user=self.users[0], ended_at__isnull=True).count(), 1)

    def test_participation_last_seats_and_duplicate_retries(self):
        results = self.parallel([lambda user=u: participate(user, self.schedule, join=True) for u in self.users])
        self.assertEqual(results.count('recruitment_full'), 2)
        self.assertEqual(Participation.objects.count(), 2)
        user = Participation.objects.first().user
        results = self.parallel([lambda: participate(user, self.schedule, join=False)]*4)
        self.assertEqual(sum(r['changed'] for r in results), 1)
        results = self.parallel([lambda: participate(user, self.schedule, join=True)]*4)
        self.assertEqual(sum(r['changed'] for r in results), 1)
        self.assertEqual(Participation.objects.count(), 2)

    def test_capacity_reduction_races_with_join(self):
        participate(self.users[0], self.schedule, join=True)
        results = self.parallel([
            lambda: configure_recruitment(self.users[0], self.schedule, {'capacity': 1}),
            lambda: participate(self.users[1], self.schedule, join=True),
        ])
        schedule = Schedule.objects.get(pk=self.schedule)
        self.assertLessEqual(schedule.participations.count(), schedule.recruitment_capacity)
        self.assertEqual(sum(isinstance(r, str) for r in results), 1)

    def test_cancel_races_with_join_and_new_joins_remain_blocked(self):
        self.parallel([lambda: cancel_schedule(self.users[0], self.schedule),
                       lambda: participate(self.users[1], self.schedule, join=True)])
        self.assertTrue(Schedule.objects.get(pk=self.schedule).is_cancelled)
        with self.assertRaises(ApiError) as exc:
            participate(self.users[2], self.schedule, join=True)
        self.assertEqual(exc.exception.code, 'schedule_closed')
        self.assertLessEqual(Participation.objects.count(), 1)

    def test_concurrent_overlap_create_on_empty_calendar(self):
        cancel_schedule(self.users[0], self.schedule)
        data = payload()
        results = self.parallel([lambda u=u: save_schedule(u, data) for u in self.users])
        self.assertEqual(results.count('schedule_overlap'), 3)
        self.assertEqual(Schedule.objects.filter(is_cancelled=False).count(), 1)

    def test_concurrent_overlap_update(self):
        from datetime import timedelta
        original = Schedule.objects.get(pk=self.schedule)
        second = save_schedule(self.users[1], payload(
            starts_at=(original.ends_at+timedelta(hours=1)).isoformat(),
            ends_at=(original.ends_at+timedelta(hours=2)).isoformat()))['id']
        target = {'starts_at':(original.ends_at+timedelta(days=2)).isoformat(),
                  'ends_at':(original.ends_at+timedelta(days=2,hours=1)).isoformat()}
        results = self.parallel([lambda: save_schedule(self.users[0], target, self.schedule),
                                 lambda: save_schedule(self.users[1], target, second)])
        self.assertEqual(results.count('schedule_overlap'), 1)
