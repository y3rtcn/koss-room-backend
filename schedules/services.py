from django.db import transaction

from realtime.events import notify_schedule_change
from spaces.models import Space
from .models import Schedule
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.http import ApiError


def validate_schedule_input(data):
    result = {}

    for field in ("title", "purpose"):
        value = data.get(field)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
            raise ApiError(
                "invalid_text",
                f"{field} 항목은 1~100자로 입력하세요.",
            )
        result[field] = value.strip()

    for field in ("space_id", "expected_count"):
        value = data.get(field)
        if type(value) is not int or not 1 <= value <= 2147483647:
            raise ApiError(
                "invalid_number",
                f"{field} 항목은 양의 정수로 입력하세요.",
            )
        result[field] = value

    for field in ("starts_at", "ends_at"):
        value = data.get(field)

        try:
            parsed = parse_datetime(value) if isinstance(value, str) else None
        except (ValueError, OverflowError):
            parsed = None

        if parsed is None or timezone.is_naive(parsed):
            raise ApiError(
                "invalid_datetime",
                f"{field} 항목에 시간대를 포함한 날짜와 시간을 입력하세요.",
            )

        result[field] = parsed

    if result["ends_at"] <= result["starts_at"]:
        raise ApiError(
            "invalid_interval",
            "종료 시간은 시작 시간보다 뒤여야 합니다.",
        )

    confirm_overlap = data.get("confirm_overlap", False)
    if type(confirm_overlap) is not bool:
        raise ApiError(
            "invalid_confirmation",
            "confirm_overlap 항목은 true 또는 false여야 합니다.",
        )

    return result, confirm_overlap

@transaction.atomic
def create_schedule(*, user, data):
    values, confirm_overlap = validate_schedule_input(data)

    try:
        space = Space.objects.select_for_update().get(
            pk=values["space_id"],
            is_active=True,
        )
    except Space.DoesNotExist:
        raise ApiError(
            "space_not_found",
            "사용 가능한 공간을 찾을 수 없습니다.",
            404,
        )

    if values["expected_count"] > space.capacity:
        raise ApiError(
            "capacity_exceeded",
            "예상 인원이 공간 정원을 초과합니다.",
        )

    overlaps = list(
        Schedule.objects.filter(
            space=space,
            is_cancelled=False,
            starts_at__lt=values["ends_at"],
            ends_at__gt=values["starts_at"],
        )
    )

    if overlaps and not confirm_overlap:
        conflicts = [
            {
                "id": schedule.pk,
                "title": schedule.title,
                "starts_at": schedule.starts_at.isoformat(),
                "ends_at": schedule.ends_at.isoformat(),
            }
            for schedule in overlaps
        ]
        return None, conflicts

    values.pop("space_id")
    schedule = Schedule.objects.create(
        creator=user,
        space=space,
        **values,
    )

    notify_schedule_change(
        schedule_id=schedule.pk,
        action="created",
    )

    return schedule, []

@transaction.atomic
def update_schedule(*, user, schedule_id, data):
    try:
        schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
    except Schedule.DoesNotExist:
        raise ApiError("schedule_not_found", "일정을 찾을 수 없습니다.", 404)

    if schedule.creator_id != user.pk:
        raise ApiError(
            "permission_denied",
            "본인이 만든 일정만 수정할 수 있습니다.",
            403,
        )

    if schedule.is_cancelled:
        raise ApiError(
            "schedule_cancelled",
            "취소된 일정은 수정할 수 없습니다.",
            409,
        )

    values, confirm_overlap = validate_schedule_input(data)

    space_ids = {schedule.space_id, values["space_id"]}
    locked_spaces = {
        space.pk: space
        for space in (
            Space.objects.select_for_update()
            .filter(pk__in=space_ids)
            .order_by("pk")
        )
    }
    space = locked_spaces.get(values["space_id"])

    if space is None or not space.is_active:
        raise ApiError(
            "space_not_found",
            "사용 가능한 공간을 찾을 수 없습니다.",
            404,
        )

    if values["expected_count"] > space.capacity:
        raise ApiError(
            "capacity_exceeded",
            "예상 인원이 공간 정원을 초과합니다.",
        )

    overlaps = list(
        Schedule.objects.filter(
            space=space,
            is_cancelled=False,
            starts_at__lt=values["ends_at"],
            ends_at__gt=values["starts_at"],
        ).exclude(pk=schedule.pk)
    )

    if overlaps and not confirm_overlap:
        return None, [
            {
                "id": item.pk,
                "title": item.title,
                "starts_at": item.starts_at.isoformat(),
                "ends_at": item.ends_at.isoformat(),
            }
            for item in overlaps
        ]

    values.pop("space_id")
    schedule.space = space
    for field, value in values.items():
        setattr(schedule, field, value)

    schedule.save()
    notify_schedule_change(schedule_id=schedule.pk, action="updated")

    return schedule, []