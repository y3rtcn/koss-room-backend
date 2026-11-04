from django.http import JsonResponse

from common.http import ApiError, api, json_body
from common.validation import fields, resource_id, timestamp
from . import services


@api(["GET", "POST"])
def schedules(request):
    if request.method == "POST":
        return JsonResponse({"schedule": services.save_schedule(request.user, json_body(request))}, status=201)
    start = timestamp(request.GET.get("start"), "start")
    end = timestamp(request.GET.get("end"), "end")
    try:
        limit, offset = int(request.GET.get("limit", 100)), int(request.GET.get("offset", 0))
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError
    except (TypeError, ValueError):
        raise ApiError("invalid_parameter", "limit은 1~100, offset은 0~100000 정수입니다.")
    return JsonResponse(services.list_schedules(request.user, start, end, limit, offset))


@api(["GET", "PATCH"])
def detail(request, schedule_id):
    pk = resource_id(schedule_id)
    if request.method == "PATCH":
        result = services.save_schedule(request.user, json_body(request), pk)
    else:
        result = services.serialize(services.get_schedule(pk), request.user)
    return JsonResponse({"schedule": result})


@api(["POST"])
def cancel(request, schedule_id):
    fields(json_body(request), set())
    return JsonResponse(services.cancel_schedule(request.user, resource_id(schedule_id)))


@api(["GET", "PUT"])
def recruitment(request, schedule_id):
    pk = resource_id(schedule_id)
    if request.method == "PUT":
        return JsonResponse(services.configure_recruitment(request.user, pk, json_body(request)))
    return JsonResponse({"recruitment": services.recruitment(services.get_schedule(pk), request.user)})


@api(["POST", "DELETE"])
def participation(request, schedule_id):
    fields(json_body(request), set())
    return JsonResponse(services.participate(request.user, resource_id(schedule_id), join=request.method == "POST"))
