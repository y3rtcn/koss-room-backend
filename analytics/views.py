from django.http import JsonResponse
from django.utils import timezone

from common.http import api, parse_date

from .services import KST, daily_statistics


@api(["GET"])
def daily(request):
    day = parse_date(request.GET.get("date", timezone.localdate(timezone=KST).isoformat()))
    return JsonResponse(daily_statistics(day))


@api(["GET"])
def summary(request):
    return JsonResponse({"is_dummy": True, "source": "fixed_example", "uses_ai": False,
                         "summary": "[예시] 이용 기록이 쌓이면 시간대별 동아리방 이용 현황을 확인할 수 있습니다."})
