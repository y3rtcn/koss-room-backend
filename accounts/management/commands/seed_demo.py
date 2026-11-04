import getpass
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from schedules.models import CalendarLock, Schedule
from schedules.services import configure_recruitment, save_schedule
from tables.models import Table


class Command(BaseCommand):
    help = "Create demo users, physical tables and a schedule without overwriting existing data."

    def handle(self, *args, **options):
        specifications = [("room-demo-a", "demo-room-a", "데모 다람쥐"),
                          ("room-demo-b", "demo-room-b", "데모 고양이")]
        missing = any(not Profile.objects.filter(demo_key=key).exists() for key, _, _ in specifications)
        password = None
        if missing:
            password = os.getenv("KOSS_DEMO_PASSWORD")
            if password is None:
                try:
                    password = getpass.getpass("새 데모 계정 비밀번호 (8자 이상): ")
                except (EOFError, KeyboardInterrupt):
                    raise CommandError("환경변수 KOSS_DEMO_PASSWORD 또는 대화형 비밀번호가 필요합니다.")
            if len(password) < 8:
                raise CommandError("데모 비밀번호는 8자 이상이어야 합니다.")
        with transaction.atomic():
            CalendarLock.objects.select_for_update().get(pk=1)
            users = []
            for key, username, nickname in specifications:
                profile = Profile.objects.select_related("user").filter(demo_key=key).first()
                if profile is None:
                    if get_user_model().objects.filter(username=username).exists():
                        raise CommandError(f"{username}: 기존 계정과 충돌합니다. 변경하지 않았습니다.")
                    user = get_user_model().objects.create_user(username=username, password=password)
                    profile = Profile.objects.create(user=user, nickname=nickname, demo_key=key)
                users.append(profile.user)
            for number, capacity in ((1, 4), (2, 4), (3, 2)):
                Table.objects.get_or_create(demo_key=f"room-demo-table-{number}",
                                            defaults={"name": f"테이블 {number}", "capacity": capacity})
            if not Schedule.objects.filter(demo_key="room-demo-schedule").exists():
                day = timezone.localdate() + timedelta(days=1)
                start = datetime.combine(day, time(18), ZoneInfo("Asia/Seoul"))
                result = save_schedule(users[0], {"title": "데모 프로젝트 모임", "description": "API 연결 확인용 예시 일정",
                    "category": "study", "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=1)).isoformat(), "confirm_overlap": True})
                schedule = Schedule.objects.get(pk=result["id"])
                schedule.demo_key = "room-demo-schedule"
                schedule.save(update_fields=["demo_key"])
                configure_recruitment(users[0], schedule.pk, {"capacity": 4})
        self.stdout.write(self.style.SUCCESS("데모 데이터 준비 완료. 기존 비밀번호·수정 데이터는 유지했습니다."))
        for user in users:
            self.stdout.write(f"로그인 ID: {user.get_username()}")
