from django.http import JsonResponse

from common.http import api


@api(["GET"])
def me(request):
    user = request.user
    return JsonResponse({
        "id": str(user.pk),
        "email": user.email,
        "nickname": user.nickname,
    })

# Create your views here.
