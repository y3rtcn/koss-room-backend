from django.http import JsonResponse

from django.db import IntegrityError, transaction

from common.http import ApiError, api, json_body
from .models import Space

from django.db.models import Count, Q
from django.utils import timezone

from schedules.models import Schedule

@api(["GET"])
def space_list(request):
    spaces = Space.objects.filter(is_active=True)

    return JsonResponse({
        "spaces": [
            {
                "id": space.pk,
                "name": space.name,
                "capacity": space.capacity,
            }
            for space in spaces
        ]
    })

@api(["POST"])
def space_create(request):
    if not request.user.is_staff:
        raise ApiError("permission_denied", "관리자만 사용할 수 있습니다.", 403)

    data = json_body(request)
    name = data.get("name")
    capacity = data.get("capacity")

    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
        raise ApiError("invalid_name", "공간 이름은 1~50자로 입력하세요.")

    if type(capacity) is not int or not 1 <= capacity <= 32767:
        raise ApiError("invalid_capacity", "정원은 1~32767의 정수로 입력하세요.")

    try:
        with transaction.atomic():
            space = Space.objects.create(
                name=name.strip(),
                capacity=capacity,
            )
    except IntegrityError:
        raise ApiError("space_conflict", "같은 이름의 공간이 이미 있습니다.", 409)

    return JsonResponse({
        "id": space.pk,
        "name": space.name,
        "capacity": space.capacity,
    }, status=201)

@api(["PATCH"])
def space_update(request, space_id):
    if not request.user.is_staff:
        raise ApiError("permission_denied", "관리자만 사용할 수 있습니다.", 403)

    capacity = json_body(request).get("capacity")
    if type(capacity) is not int or not 1 <= capacity <= 32767:
        raise ApiError("invalid_capacity", "정원은 1~32767의 정수로 입력하세요.")

    with transaction.atomic():
        try:
            space = Space.objects.select_for_update().get(pk=space_id)
        except Space.DoesNotExist:
            raise ApiError("space_not_found", "공간을 찾을 수 없습니다.", 404)

        if capacity < space.capacity:
            has_conflict = (
                Schedule.objects.filter(
                    space=space,
                    is_cancelled=False,
                    ends_at__gt=timezone.now(),
                )
                .annotate(participant_count=Count("participations"))
                .filter(
                    Q(expected_count__gt=capacity)
                    | Q(participant_count__gt=capacity)
                )
                .exists()
            )
            if has_conflict:
                raise ApiError(
                    "space_capacity_conflict",
                    "기존 일정의 모집 정원 또는 참여 인원보다 공간 정원을 줄일 수 없습니다.",
                    409,
                )

        space.capacity = capacity
        space.save(update_fields=["capacity"])

    return JsonResponse({
        "id": space.pk,
        "capacity": space.capacity,
    })