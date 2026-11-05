from django.http import JsonResponse

from common.http import ApiError, api, json_body
from .services import (
    create_schedule,
    update_schedule,
    cancel_schedule,
    join_schedule,
)
from .models import Schedule


def schedule_data(schedule):
    return {
        "id": schedule.pk,
        "title": schedule.title,
        "creator_id": str(schedule.creator_id),
        "space_id": schedule.space_id,
        "space_name": schedule.space.name,
        "starts_at": schedule.starts_at.isoformat(),
        "ends_at": schedule.ends_at.isoformat(),
        "expected_count": schedule.expected_count,
        "purpose": schedule.purpose,
        "is_cancelled": schedule.is_cancelled,
    }


@api(["GET"])
def schedule_list(request):
    schedules = (
        Schedule.objects
        .filter(is_cancelled=False)
        .select_related("space")
    )

    return JsonResponse({
        "schedules": [schedule_data(schedule) for schedule in schedules]
    })

@api(["POST"])
def schedule_create(request):
    schedule, conflicts = create_schedule(
        user=request.user,
        data=json_body(request),
    )

    if schedule is None:
        return JsonResponse({
            "error": {
                "code": "schedule_overlap",
                "message": "같은 공간에 겹치는 일정이 있습니다. 확인 후 다시 요청하세요.",
            },
            "conflicts": conflicts,
        }, status=409)

    return JsonResponse({
        "schedule": schedule_data(schedule),
    }, status=201)

@api(["GET"])
def schedule_detail(request, schedule_id):
    try:
        schedule = (
            Schedule.objects
            .select_related("space")
            .get(pk=schedule_id)
        )
    except Schedule.DoesNotExist:
        raise ApiError(
            "schedule_not_found",
            "일정을 찾을 수 없습니다.",
            404,
        )

    return JsonResponse({
        "schedule": schedule_data(schedule),
    })

@api(["PUT"])
def schedule_update(request, schedule_id):
    schedule, conflicts = update_schedule(
        user=request.user,
        schedule_id=schedule_id,
        data=json_body(request),
    )

    if schedule is None:
        return JsonResponse({
            "error": {
                "code": "schedule_overlap",
                "message": "같은 공간에 겹치는 일정이 있습니다. 확인 후 다시 요청하세요.",
            },
            "conflicts": conflicts,
        }, status=409)

    return JsonResponse({
        "schedule": schedule_data(schedule),
    })

@api(["POST"])
def schedule_cancel(request, schedule_id):
    schedule, changed = cancel_schedule(
        user=request.user,
        schedule_id=schedule_id,
    )

    return JsonResponse({
        "schedule": schedule_data(schedule),
        "changed": changed,
    })

@api(["POST"])
def schedule_join(request, schedule_id):
    schedule, changed = join_schedule(
        user=request.user,
        schedule_id=schedule_id,
    )

    return JsonResponse({
        "schedule_id": schedule.pk,
        "changed": changed,
        "participant_count": schedule.participations.count(),
        "capacity": schedule.expected_count,
    })


@api(["GET"])
def participant_list(request, schedule_id):
    try:
        schedule = Schedule.objects.get(pk=schedule_id)
    except Schedule.DoesNotExist:
        raise ApiError("schedule_not_found", "일정을 찾을 수 없습니다.", 404)

    participations = list(
        schedule.participations.select_related("user")
    )

    return JsonResponse({
        "schedule_id": schedule.pk,
        "capacity": schedule.expected_count,
        "participant_count": len(participations),
        "participants": [
            {
                "user_id": str(item.user_id),
                "nickname": item.user.nickname or "동아리원",
                "is_creator": item.user_id == schedule.creator_id,
            }
            for item in participations
        ],
    })