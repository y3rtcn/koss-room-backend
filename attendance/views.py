from django.http import JsonResponse

from common.http import api

from .services import set_presence, status


@api(["GET"])
def me(request):
    return JsonResponse(status(request.user))


@api(["GET"])
def occupancy(request):
    snapshot = status(request.user)
    return JsonResponse({key: snapshot[key] for key in ("current_count", "revision")})


@api(["POST"])
def check_in(request):
    return JsonResponse(set_presence(request.user, inside=True))


@api(["POST"])
def check_out(request):
    return JsonResponse(set_presence(request.user, inside=False))
