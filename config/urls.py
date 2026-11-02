from django.urls import include, path

from common.http import csrf_token

urlpatterns = [
    path("api/csrf/", csrf_token),
    path("api/attendance/", include("attendance.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/analytics/", include("analytics.urls")),
]
