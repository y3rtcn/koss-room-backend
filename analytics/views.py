from django.http import JsonResponse
from django.utils import timezone

from common.http import ApiError, api, parse_date
from spaces.models import Space

from .recommendations import space_recommendations

from .services import KST, daily_statistics


@api(["GET"])
def daily(request):
    day = parse_date(request.GET.get("date", timezone.localdate(timezone=KST).isoformat()))
    return JsonResponse(daily_statistics(day))


@api(["GET"])
def summary(request):
    return JsonResponse({"is_dummy": True, "source": "fixed_example", "uses_ai": False,
                         "summary": "[예시] 이용 기록이 쌓이면 시간대별 동아리방 이용 현황을 확인할 수 있습니다."})


@api(["GET"])
def recommendations(request):
    day = parse_date(request.GET.get("date", timezone.localdate(timezone=KST).isoformat()))
    raw_id = request.GET.get("space_id", "")
    if not raw_id.isascii() or not raw_id.isdecimal() or len(raw_id) > 10:
        raise ApiError("invalid_space_id", "space_id에 양의 정수를 입력하세요.")
    space_id = int(raw_id)
    if not 1 <= space_id <= 2147483647:
        raise ApiError("invalid_space_id", "space_id 범위를 확인하세요.")
    space = Space.objects.filter(pk=space_id, is_active=True).first()
    if space is None:
        raise ApiError("space_not_found", "사용 가능한 공간이 없습니다.", 404)
    return JsonResponse(space_recommendations(space, day))
