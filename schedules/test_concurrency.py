from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from common.http import ApiError
from spaces.models import Space
from .models import Schedule
from .services import create_schedule, join_schedule
from datetime import timedelta

from django.utils import timezone

@skipUnless(connection.vendor == "postgresql", "PostgreSQL 전용 테스트")
class ParticipationConcurrencyTests(TransactionTestCase):
    def test_only_one_member_gets_last_place(self):
        User = get_user_model()
        creator = User.objects.create_user(
            username="concurrent-creator",
            email="concurrent-creator@kookmin.ac.kr",
        )
        members = [
            User.objects.create_user(
                username=f"concurrent-member-{i}",
                email=f"concurrent-member-{i}@kookmin.ac.kr",
            )
            for i in range(2)
        ]
        space = Space.objects.create(name="동시 신청 공간", capacity=4)
        starts_at = timezone.now() + timedelta(days=1)
        schedule, _ = create_schedule(
            user=creator,
            data={
                "title": "마지막 한 자리",
                "space_id": space.pk,
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                "expected_count": 2,
                "purpose": "스터디",
            },
        )
        schedule_id = schedule.pk
        barrier = Barrier(2)

        def apply(user_id):
            close_old_connections()
            try:
                user = User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    _, changed = join_schedule(
                        user=user,
                        schedule_id=schedule_id,
                    )
                    return "joined" if changed else "already_joined"
                except ApiError as exc:
                    return exc.code
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                apply,
                [member.pk for member in members],
            ))

        self.assertCountEqual(results, ["joined", "schedule_full"])
        schedule = Schedule.objects.get(pk=schedule_id)
        self.assertEqual(schedule.participations.count(), 2)
        self.assertTrue(
            schedule.participations.filter(user=creator).exists()
        )

@skipUnless(connection.vendor == "postgresql", "PostgreSQL 전용 테스트")
class ScheduleCreationConcurrencyTests(TransactionTestCase):
    def test_simultaneous_overlapping_creation_requires_confirmation(self):
        User = get_user_model()
        creators = [
            User.objects.create_user(
                username=f"concurrent-scheduler-{i}",
                email=f"concurrent-scheduler-{i}@kookmin.ac.kr",
            )
            for i in range(2)
        ]
        space = Space.objects.create(name="동시 예약 공간", capacity=4)
        payload = {
            "title": "동시 예약",
            "space_id": space.pk,
            "starts_at": "2026-11-10T14:00:00+09:00",
            "ends_at": "2026-11-10T15:00:00+09:00",
            "expected_count": 2,
            "purpose": "스터디",
        }
        barrier = Barrier(2)

        def apply(user_id):
            close_old_connections()
            try:
                user = User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                schedule, conflicts = create_schedule(
                    user=user,
                    data=payload,
                )
                if schedule is not None:
                    return "created"
                return "conflict" if conflicts else "unexpected"
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                apply,
                [creator.pk for creator in creators],
            ))

        self.assertCountEqual(results, ["created", "conflict"])
        self.assertEqual(Schedule.objects.count(), 1)
        schedule = Schedule.objects.get()
        self.assertEqual(schedule.participations.count(), 1)
        self.assertTrue(
            schedule.participations.filter(
                user_id=schedule.creator_id
            ).exists()
        )