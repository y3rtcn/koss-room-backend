from django.http import JsonResponse

from django.db import IntegrityError, transaction

from common.http import ApiError, api, json_body
from .models import Space


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
# Create your views here.
