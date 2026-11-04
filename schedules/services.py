from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from accounts.nicknames import display_nickname
from common.http import ApiError
from common.validation import fields, integer, interval, text, timestamp
from realtime.events import notify_schedule_change
from .models import CalendarLock, Participation, Schedule


def get_schedule(pk, *, lock=False):
    query = Schedule.objects.select_for_update() if lock else Schedule.objects.all()
    try:
        return query.get(pk=pk)
    except Schedule.DoesNotExist:
        raise ApiError("not_found", "일정을 찾을 수 없습니다.", 404)


def owner(schedule, user):
    if schedule.author_id != user.pk:
        raise ApiError("permission_denied", "일정 작성자만 변경할 수 있습니다.", 403)


def recruitment(schedule, user):
    count = getattr(schedule, "participant_count", None)
    joined = getattr(schedule, "joined_by_me", None)
    return {"capacity": schedule.recruitment_capacity,
            "participant_count": count if count is not None else schedule.participations.count(),
            "is_participating": joined if joined is not None else schedule.participations.filter(user=user).exists()}


def serialize(schedule, user):
    return {"id": schedule.pk, "title": schedule.title, "description": schedule.description,
            "category": schedule.category, "starts_at": schedule.starts_at.isoformat(),
            "ends_at": schedule.ends_at.isoformat(),
            "author": {"id": str(schedule.author_id), "nickname": display_nickname(schedule.author)},
            "is_cancelled": schedule.is_cancelled,
            "created_at": schedule.created_at.isoformat(), "updated_at": schedule.updated_at.isoformat(),
            "recruitment": recruitment(schedule, user)}


def list_schedules(user, start, end, limit, offset):
    interval(start, end)
    if end - start > timedelta(days=366):
        raise ApiError("invalid_interval", "조회 기간은 최대 366일입니다.")
    query = Schedule.objects.filter(starts_at__lt=end, ends_at__gt=start).select_related(
        "author", "author__room_profile"
    ).annotate(participant_count=Count("participations"), joined_by_me=Exists(
        Participation.objects.filter(schedule_id=OuterRef("pk"), user=user)
    ))
    rows = list(query.order_by("starts_at", "id")[offset:offset + limit + 1])
    return {"schedules": [serialize(s, user) for s in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None}


@transaction.atomic
def save_schedule(user, data, pk=None):
    fields(data, {"title", "description", "category", "starts_at", "ends_at", "confirm_overlap"})
    if "confirm_overlap" in data and type(data["confirm_overlap"]) is not bool:
        raise ApiError("invalid_parameter", "confirm_overlap는 boolean입니다.")
    # This independent A lock never changes B's OccupancyState.
    CalendarLock.objects.select_for_update().get(pk=1)
    schedule = get_schedule(pk, lock=True) if pk is not None else Schedule(author=user)
    if pk is not None:
        owner(schedule, user)
        if schedule.is_cancelled:
            raise ApiError("schedule_cancelled", "취소된 일정은 수정할 수 없습니다.", 409)
    for name, maximum, blank in (("title", 120, False), ("description", 4000, True), ("category", 80, False)):
        if name in data or (pk is None and name == "title"):
            setattr(schedule, name, text(data.get(name), name, maximum, blank=blank))
    for name in ("starts_at", "ends_at"):
        if name in data or pk is None:
            setattr(schedule, name, timestamp(data.get(name), name))
    interval(schedule.starts_at, schedule.ends_at)
    conflicts = Schedule.objects.filter(is_cancelled=False, starts_at__lt=schedule.ends_at,
                                         ends_at__gt=schedule.starts_at).exclude(pk=schedule.pk)
    if not data.get("confirm_overlap", False):
        rows = list(conflicts.order_by("starts_at", "id")[:101])
        if rows:
            raise ApiError("schedule_overlap", "겹치는 일정을 확인한 뒤 confirm_overlap=true로 다시 요청하세요.", 409,
                           details={"conflicts": [{"id": s.pk, "title": s.title,
                                    "starts_at": s.starts_at.isoformat(), "ends_at": s.ends_at.isoformat()}
                                   for s in rows[:100]], "has_more": len(rows) > 100})
    schedule.save()
    notify_schedule_change(schedule_id=schedule.pk, action="created" if pk is None else "updated")
    return serialize(schedule, user)


@transaction.atomic
def cancel_schedule(user, pk):
    CalendarLock.objects.select_for_update().get(pk=1)
    schedule = get_schedule(pk, lock=True)
    owner(schedule, user)
    changed = not schedule.is_cancelled
    if changed:
        schedule.is_cancelled = True
        schedule.save(update_fields=["is_cancelled", "updated_at"])
        notify_schedule_change(schedule_id=schedule.pk, action="cancelled")
    return {"schedule": serialize(schedule, user), "changed": changed}


@transaction.atomic
def configure_recruitment(user, pk, data):
    fields(data, {"capacity"})
    if "capacity" not in data:
        raise ApiError("invalid_parameter", "capacity가 필요합니다.")
    capacity = data["capacity"]
    if capacity is not None:
        integer(capacity, "capacity")
    schedule = get_schedule(pk, lock=True)
    owner(schedule, user)
    if schedule.is_cancelled or schedule.ends_at <= timezone.now():
        raise ApiError("schedule_closed", "취소되거나 종료된 일정의 모집은 변경할 수 없습니다.", 409)
    if (capacity or 0) < schedule.participations.count():
        raise ApiError("capacity_below_count", "정원은 현재 참여 인원보다 작을 수 없습니다.", 409)
    changed = schedule.recruitment_capacity != capacity
    if changed:
        schedule.recruitment_capacity = capacity
        schedule.save(update_fields=["recruitment_capacity", "updated_at"])
        notify_schedule_change(schedule_id=schedule.pk, action="updated")
    return {"recruitment": recruitment(schedule, user), "changed": changed}


@transaction.atomic
def participate(user, pk, *, join):
    schedule = get_schedule(pk, lock=True)
    existing = schedule.participations.filter(user=user)
    changed = False
    if not join:
        changed = existing.delete()[0] > 0
    elif not existing.exists():
        if schedule.is_cancelled or schedule.ends_at <= timezone.now():
            raise ApiError("schedule_closed", "취소되거나 종료된 일정에는 참여할 수 없습니다.", 409)
        if schedule.recruitment_capacity is None:
            raise ApiError("recruitment_disabled", "모집이 설정되지 않았습니다.", 409)
        if schedule.participations.count() >= schedule.recruitment_capacity:
            raise ApiError("recruitment_full", "모집 정원이 찼습니다.", 409)
        Participation.objects.create(schedule=schedule, user=user)
        changed = True
    if changed:
        notify_schedule_change(schedule_id=schedule.pk, action="updated")
    return {"recruitment": recruitment(schedule, user), "changed": changed}
