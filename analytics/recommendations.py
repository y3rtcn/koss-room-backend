"""Adapt current database state to the data team's analysis contract."""
from datetime import datetime, time, timedelta

from django.db.models import Prefetch
from django.utils import timezone

from koss_data import analyze
from schedules.models import Participation, Schedule

from .services import KST


def space_recommendations(space, day):
    start = datetime.combine(day, time.min, KST)
    end = start + timedelta(days=1)
    schedules = Schedule.objects.filter(
        space=space, is_cancelled=False, starts_at__lt=end, ends_at__gt=start,
    ).prefetch_related(Prefetch(
        "participations", queryset=Participation.objects.only("schedule_id", "user_id"),
    ))
    rows, participants = [], {}
    for schedule in schedules:
        users = list(schedule.participations.all())
        rows.append({
            "id": schedule.pk, "space_id": space.pk,
            "starts_at": schedule.starts_at.isoformat(),
            "ends_at": schedule.ends_at.isoformat(),
            "expected_count": schedule.expected_count, "is_cancelled": False,
        })
        participants[str(schedule.pk)] = {
            "schedule_id": schedule.pk, "participant_count": len(users),
            "participants": [{"user_id": str(p.user_id)} for p in users],
        }
    result = analyze(
        {"spaces": [{"id": space.pk}], "schedules": rows,
         "participants": participants},
        day, capacity=space.capacity, space_ids=[space.pk],
        room_scope=False, history_start=None, now=timezone.now(),
    )
    result["limitations"].extend([
        "공간별 예약 분석입니다. 동방 전체 입퇴실·채팅 인원은 적용하지 않습니다.",
        "과거 기록의 완전 보존 기간이 확인되지 않아 과거 통계와 확정 추천은 제공하지 않습니다.",
        "공간·일정·참여자는 조회 중 변경될 수 있습니다. 변경 알림 후 다시 조회하세요.",
        "운영 시간을 반영하지 않은 하루 24개 시간대입니다.",
    ])
    return result
