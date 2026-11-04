import json
import re
from datetime import date
from functools import wraps

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache


class ApiError(Exception):
    def __init__(self, code, message, status=400, *, details=None):
        self.code, self.message, self.status = code, message, status
        self.details = details


def error_response(code, message, status, *, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JsonResponse({"error": error}, status=status)


def api(methods, *, authenticated=True):
    def decorate(view):
        @never_cache
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if authenticated and (not request.user.is_authenticated or not request.user.is_active):
                return error_response("authentication_required", "로그인이 필요합니다.", 401)
            if request.method not in methods:
                response = error_response("method_not_allowed", "지원하지 않는 메서드입니다.", 405)
                response["Allow"] = ", ".join(methods)
                return response
            try:
                return view(request, *args, **kwargs)
            except ApiError as exc:
                return error_response(exc.code, exc.message, exc.status, details=exc.details)
            except RequestDataTooBig:
                return error_response("body_too_large", "요청 본문이 너무 큽니다.", 413)
        return wrapped
    return decorate


def json_body(request):
    if request.content_type != "application/json":
        raise ApiError("invalid_content_type", "application/json을 사용하세요.", 415)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError("invalid_json", "올바른 JSON 객체가 필요합니다.")
    if not isinstance(data, dict):
        raise ApiError("invalid_json", "JSON 객체가 필요합니다.")
    return data


def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ApiError("invalid_date", "날짜는 YYYY-MM-DD 형식입니다.")
    try:
        parsed = date.fromisoformat(value)
        if parsed in (date.min, date.max):
            raise ValueError
        return parsed
    except ValueError:
        raise ApiError("invalid_date", "0001-01-02~9999-12-30 범위의 날짜를 입력하세요.")


@never_cache
def csrf_token(request):
    if request.method != "GET":
        return error_response("method_not_allowed", "GET을 사용하세요.", 405)
    return JsonResponse({"csrf_token": get_token(request)})


def csrf_failure(request, reason=""):
    return error_response("csrf_failed", "CSRF 토큰과 세션 쿠키를 확인하세요.", 403)
