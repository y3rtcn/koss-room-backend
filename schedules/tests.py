from django.contrib.auth import get_user_model
from django.test import TestCase

from spaces.models import Space
from .models import Schedule


class ScheduleCreateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="schedule-member",
            email="schedule-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        self.space = Space.objects.create(name="일정 테스트 공간", capacity=4)
        self.payload = {
            "title": "스터디",
            "space_id": self.space.pk,
            "starts_at": "2026-11-10T14:00:00+09:00",
            "ends_at": "2026-11-10T15:00:00+09:00",
            "expected_count": 3,
            "purpose": "공부",
        }

    def post(self, **changes):
        data = {**self.payload, **changes}
        return self.client.post(
            "/api/schedules/create/",
            data=data,
            content_type="application/json",
        )

    def test_create_schedule(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        schedule = Schedule.objects.get()
        self.assertEqual(schedule.creator, self.user)
        self.assertEqual(schedule.space, self.space)
        self.assertEqual(schedule.expected_count, 3)

    def test_overlap_requires_confirmation(self):
        self.post()
        response = self.post(title="겹치는 일정")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "schedule_overlap")
        self.assertEqual(len(response.json()["conflicts"]), 1)
        self.assertEqual(Schedule.objects.count(), 1)

    def test_confirmed_overlap_can_be_created(self):
        self.post()
        response = self.post(
            title="확인한 일정",
            confirm_overlap=True,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Schedule.objects.count(), 2)

    def test_adjacent_times_do_not_overlap(self):
        self.post()
        response = self.post(
            starts_at="2026-11-10T15:00:00+09:00",
            ends_at="2026-11-10T16:00:00+09:00",
        )

        self.assertEqual(response.status_code, 201)

    def test_capacity_exceeded(self):
        response = self.post(expected_count=5)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Schedule.objects.exists())

    def test_invalid_interval(self):
        response = self.post(
            ends_at="2026-11-10T13:00:00+09:00",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Schedule.objects.exists())

    def test_inactive_space_is_rejected(self):
        self.space.is_active = False
        self.space.save(update_fields=["is_active"])

        response = self.post()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Schedule.objects.exists())

    def test_login_required(self):
        self.client.logout()
        response = self.post()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Schedule.objects.exists())

class ScheduleDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="detail-member",
            email="detail-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        space = Space.objects.create(name="상세 조회 공간", capacity=4)

        from django.utils.dateparse import parse_datetime

        self.schedule = Schedule.objects.create(
            title="상세 조회 스터디",
            creator=self.user,
            space=space,
            starts_at=parse_datetime("2026-11-10T14:00:00+09:00"),
            ends_at=parse_datetime("2026-11-10T15:00:00+09:00"),
            expected_count=3,
            purpose="공부",
        )
        self.url = f"/api/schedules/{self.schedule.pk}/"

    def test_returns_schedule(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["schedule"]
        self.assertEqual(data["id"], self.schedule.pk)
        self.assertEqual(data["title"], "상세 조회 스터디")
        self.assertEqual(data["creator_id"], str(self.user.pk))
        self.assertEqual(data["space_id"], self.schedule.space_id)

    def test_cancelled_schedule_can_be_viewed(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["schedule"]["is_cancelled"])

    def test_missing_schedule_returns_404(self):
        missing_id = self.schedule.pk + 1
        response = self.client.get(f"/api/schedules/{missing_id}/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["code"],
            "schedule_not_found",
        )

    def test_login_required(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

class ScheduleUpdateTests(TestCase):
    def setUp(self):
        from django.utils.dateparse import parse_datetime

        self.user = get_user_model().objects.create_user(
            username="update-member",
            email="update-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        self.space = Space.objects.create(name="수정 테스트 공간", capacity=4)
        self.schedule = Schedule.objects.create(
            title="기존 일정",
            creator=self.user,
            space=self.space,
            starts_at=parse_datetime("2026-11-10T14:00:00+09:00"),
            ends_at=parse_datetime("2026-11-10T15:00:00+09:00"),
            expected_count=3,
            purpose="공부",
        )
        self.url = f"/api/schedules/{self.schedule.pk}/update/"
        self.payload = {
            "title": "수정된 일정",
            "space_id": self.space.pk,
            "starts_at": "2026-11-10T14:00:00+09:00",
            "ends_at": "2026-11-10T15:00:00+09:00",
            "expected_count": 4,
            "purpose": "회의",
        }

    def put(self, **changes):
        return self.client.put(
            self.url,
            data={**self.payload, **changes},
            content_type="application/json",
        )

    def add_conflicting_schedule(self):
        return Schedule.objects.create(
            title="다른 일정",
            creator=self.user,
            space=self.space,
            starts_at=self.schedule.starts_at,
            ends_at=self.schedule.ends_at,
            expected_count=2,
            purpose="회의",
        )

    def test_creator_can_update_without_self_conflict(self):
        response = self.put()

        self.assertEqual(response.status_code, 200)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.title, "수정된 일정")
        self.assertEqual(self.schedule.expected_count, 4)
        self.assertEqual(self.schedule.creator, self.user)

    def test_other_user_cannot_update(self):
        other = get_user_model().objects.create_user(
            username="other-editor",
            email="other-editor@kookmin.ac.kr",
        )
        self.client.force_login(other)

        response = self.put()

        self.assertEqual(response.status_code, 403)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.title, "기존 일정")

    def test_overlap_requires_confirmation(self):
        conflict = self.add_conflicting_schedule()

        response = self.put()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["conflicts"][0]["id"],
            conflict.pk,
        )
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.title, "기존 일정")

    def test_confirmed_overlap_can_be_updated(self):
        self.add_conflicting_schedule()

        response = self.put(confirm_overlap=True)

        self.assertEqual(response.status_code, 200)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.title, "수정된 일정")

    def test_cancelled_schedule_cannot_be_updated(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])

        response = self.put()

        self.assertEqual(response.status_code, 409)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.title, "기존 일정")

    def test_new_space_capacity_is_checked(self):
        smaller = Space.objects.create(name="작은 공간", capacity=2)

        response = self.put(space_id=smaller.pk)

        self.assertEqual(response.status_code, 400)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.space_id, self.space.pk)

    def test_login_required(self):
        self.client.logout()

        response = self.put()

        self.assertEqual(response.status_code, 401)

class ScheduleCancelTests(TestCase):
    def setUp(self):
        from django.utils.dateparse import parse_datetime

        self.user = get_user_model().objects.create_user(
            username="cancel-member",
            email="cancel-member@kookmin.ac.kr",
        )
        self.client.force_login(self.user)
        space = Space.objects.create(name="취소 테스트 공간", capacity=4)
        self.schedule = Schedule.objects.create(
            title="취소할 일정",
            creator=self.user,
            space=space,
            starts_at=parse_datetime("2026-11-10T14:00:00+09:00"),
            ends_at=parse_datetime("2026-11-10T15:00:00+09:00"),
            expected_count=3,
            purpose="공부",
        )
        self.url = f"/api/schedules/{self.schedule.pk}/cancel/"

    def test_creator_can_cancel(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["changed"])
        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_cancelled)
        self.assertEqual(Schedule.objects.count(), 1)

    def test_repeated_cancel_does_not_send_another_notification(self):
        from unittest.mock import patch

        with patch("schedules.services.notify_schedule_change") as notify:
            first = self.client.post(self.url)
            second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["changed"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["changed"])
        notify.assert_called_once_with(
            schedule_id=self.schedule.pk,
            action="cancelled",
        )

    def test_other_user_cannot_cancel(self):
        other = get_user_model().objects.create_user(
            username="other-canceller",
            email="other-canceller@kookmin.ac.kr",
        )
        self.client.force_login(other)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cancelled)

    def test_cancelled_schedule_is_hidden_from_list(self):
        self.client.post(self.url)

        response = self.client.get("/api/schedules/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schedules"], [])

    def test_missing_schedule_returns_404(self):
        missing_id = self.schedule.pk + 1

        response = self.client.post(
            f"/api/schedules/{missing_id}/cancel/"
        )

        self.assertEqual(response.status_code, 404)

    def test_login_required(self):
        self.client.logout()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 401)
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cancelled)

class ParticipationTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="activity-creator",
            email="activity-creator@kookmin.ac.kr",
            nickname="작성자",
        )
        self.member = get_user_model().objects.create_user(
            username="activity-member",
            email="activity-member@kookmin.ac.kr",
            nickname="참여자",
        )
        self.client.force_login(self.creator)
        self.space = Space.objects.create(name="참여 테스트 공간", capacity=4)
        self.payload = {
            "title": "참여 테스트",
            "space_id": self.space.pk,
            "starts_at": "2026-11-10T14:00:00+09:00",
            "ends_at": "2026-11-10T15:00:00+09:00",
            "expected_count": 2,
            "purpose": "스터디",
        }
        response = self.client.post(
            "/api/schedules/create/",
            data=self.payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.schedule = Schedule.objects.get(
            pk=response.json()["schedule"]["id"]
        )
        self.join_url = f"/api/schedules/{self.schedule.pk}/join/"
        self.list_url = f"/api/schedules/{self.schedule.pk}/participants/"

    def test_creator_automatically_participates(self):
        self.assertEqual(self.schedule.participations.count(), 1)
        self.assertTrue(
            self.schedule.participations.filter(user=self.creator).exists()
        )

    def test_member_can_join(self):
        self.client.force_login(self.member)

        response = self.client.post(self.join_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["changed"])
        self.assertEqual(response.json()["participant_count"], 2)

    def test_repeated_join_does_not_duplicate(self):
        self.client.force_login(self.member)
        self.client.post(self.join_url)

        response = self.client.post(self.join_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["changed"])
        self.assertEqual(self.schedule.participations.count(), 2)

    def test_full_schedule_rejects_another_member(self):
        self.client.force_login(self.member)
        self.client.post(self.join_url)
        other = get_user_model().objects.create_user(
            username="extra-member",
            email="extra-member@kookmin.ac.kr",
        )
        self.client.force_login(other)

        response = self.client.post(self.join_url)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "schedule_full")
        self.assertEqual(self.schedule.participations.count(), 2)

    def test_cancelled_schedule_rejects_join(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])
        self.client.force_login(self.member)

        response = self.client.post(self.join_url)

        self.assertEqual(response.status_code, 409)
        self.assertFalse(
            self.schedule.participations.filter(user=self.member).exists()
        )

    def test_participant_list_identifies_creator(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["participants"], [
            {
                "user_id": str(self.creator.pk),
                "nickname": "작성자",
                "is_creator": True,
            }
        ])

    def test_capacity_cannot_be_lowered_below_participants(self):
        self.client.force_login(self.member)
        self.client.post(self.join_url)
        self.client.force_login(self.creator)

        response = self.client.put(
            f"/api/schedules/{self.schedule.pk}/update/",
            data={**self.payload, "expected_count": 1},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.expected_count, 2)

    def test_login_required(self):
        self.client.logout()

        self.assertEqual(self.client.post(self.join_url).status_code, 401)
        self.assertEqual(self.client.get(self.list_url).status_code, 401)

class ParticipationLeaveTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="leave-creator",
            email="leave-creator@kookmin.ac.kr",
        )
        self.member = get_user_model().objects.create_user(
            username="leave-member",
            email="leave-member@kookmin.ac.kr",
        )
        self.client.force_login(self.creator)
        space = Space.objects.create(name="참여 취소 공간", capacity=4)

        response = self.client.post(
            "/api/schedules/create/",
            data={
                "title": "참여 취소 테스트",
                "space_id": space.pk,
                "starts_at": "2026-11-10T14:00:00+09:00",
                "ends_at": "2026-11-10T15:00:00+09:00",
                "expected_count": 2,
                "purpose": "스터디",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.schedule = Schedule.objects.get(
            pk=response.json()["schedule"]["id"]
        )
        self.join_url = f"/api/schedules/{self.schedule.pk}/join/"
        self.leave_url = f"/api/schedules/{self.schedule.pk}/leave/"
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.join_url).status_code, 200)

    def test_member_can_leave(self):
        response = self.client.post(self.leave_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["changed"])
        self.assertEqual(response.json()["participant_count"], 1)
        self.assertFalse(
            self.schedule.participations.filter(user=self.member).exists()
        )

    def test_repeated_leave_does_not_notify_again(self):
        from unittest.mock import patch

        with patch("schedules.services.notify_schedule_change") as notify:
            first = self.client.post(self.leave_url)
            second = self.client.post(self.leave_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["changed"])
        notify.assert_called_once_with(
            schedule_id=self.schedule.pk,
            action="updated",
        )

    def test_creator_cannot_leave(self):
        self.client.force_login(self.creator)

        response = self.client.post(self.leave_url)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"],
            "creator_cannot_leave",
        )
        self.assertTrue(
            self.schedule.participations.filter(user=self.creator).exists()
        )

    def test_another_member_can_fill_vacancy(self):
        self.client.post(self.leave_url)
        other = get_user_model().objects.create_user(
            username="replacement-member",
            email="replacement-member@kookmin.ac.kr",
        )
        self.client.force_login(other)

        response = self.client.post(self.join_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["changed"])
        self.assertEqual(self.schedule.participations.count(), 2)

    def test_leave_cannot_remove_another_user(self):
        other = get_user_model().objects.create_user(
            username="unrelated-member",
            email="unrelated-member@kookmin.ac.kr",
        )
        self.client.force_login(other)

        response = self.client.post(
            self.leave_url,
            data={"user_id": self.member.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["changed"])
        self.assertTrue(
            self.schedule.participations.filter(user=self.member).exists()
        )

    def test_cancelled_schedule_keeps_participation_records(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])

        response = self.client.post(self.leave_url)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.schedule.participations.count(), 2)

    def test_missing_schedule_returns_404(self):
        response = self.client.post(
            f"/api/schedules/{self.schedule.pk + 1}/leave/"
        )

        self.assertEqual(response.status_code, 404)

    def test_login_required(self):
        self.client.logout()

        response = self.client.post(self.leave_url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.schedule.participations.count(), 2)