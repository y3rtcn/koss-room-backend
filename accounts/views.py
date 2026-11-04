from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token

from common.http import ApiError, api, json_body
from common.validation import fields, text
from .nicknames import display_nickname


def serialize_user(user):
    return {"id": str(user.pk), "nickname": display_nickname(user)}


@api(["POST"], authenticated=False)
def login_view(request):
    data = json_body(request)
    fields(data, {"username", "password"})
    username = text(data.get("username"), "username", 150)
    password = data.get("password")
    if not isinstance(password, str) or not password or len(password) > 4096:
        raise ApiError("invalid_credentials", "로그인 정보가 올바르지 않습니다.", 401)
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError("invalid_credentials", "로그인 정보가 올바르지 않습니다.", 401)
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        raise ApiError("invalid_credentials", "로그인 정보가 올바르지 않습니다.", 401)
    login(request, user)
    return JsonResponse({"user": serialize_user(user), "csrf_token": get_token(request)})


@api(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"logged_out": True})


@api(["GET"])
def me(request):
    return JsonResponse({"user": serialize_user(request.user)})
