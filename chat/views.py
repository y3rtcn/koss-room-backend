from django.http import JsonResponse
from django.utils import timezone

from common.http import ApiError, api, json_body, parse_date

from .services import KST, list_messages, save_message


def positive_int(value, name, maximum=9223372036854775807):
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        raise ApiError("invalid_parameter", f"{name}은 양의 정수입니다.")
    if not 1 <= parsed <= maximum:
        raise ApiError("invalid_parameter", f"{name}은 1~{maximum} 범위입니다.")
    return parsed


@api(["GET", "POST"])
def messages(request):
    if request.method == "POST":
        message, created = save_message(request.user, json_body(request))
        return JsonResponse({"message": message, "created": created}, status=201 if created else 200)
    day = parse_date(request.GET.get("date", timezone.localdate(timezone=KST).isoformat()))
    limit = positive_int(request.GET.get("limit", "50"), "limit", 100)
    cursors = {name: positive_int(request.GET[name], name) if name in request.GET else None
               for name in ("before_id", "after_id")}
    if all(value is not None for value in cursors.values()):
        raise ApiError("invalid_parameter", "before_id와 after_id는 함께 사용할 수 없습니다.")
    return JsonResponse(list_messages(day, limit=limit, **cursors))
