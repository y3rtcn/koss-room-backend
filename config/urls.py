from django.urls import include, path, re_path

from common.http import csrf_token
from config import frontend

urlpatterns = [
    # 프론트 화면 (config/frontend.py, docs/frontend-deploy.md)
    path("", frontend.index),
    path("assets/<path:path>", frontend.asset),
    re_path(
        r"^(?P<path>[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:ico|svg|png|jpg|jpeg|webp|webmanifest|txt))$",
        frontend.root_file,
    ),
    # 기존 API·로그인 경로
    path("api/csrf/", csrf_token),
    path("api/attendance/", include("attendance.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("accounts/", include("allauth.urls")),
    path("api/accounts/", include("accounts.urls")),
    path("api/spaces/", include("spaces.urls")),
    path("api/schedules/", include("schedules.urls")),
]
