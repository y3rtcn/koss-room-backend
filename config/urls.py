from django.urls import include, path

from common.http import csrf_token
from webui import views as webui_views

urlpatterns = [
    path("", webui_views.index),
    path("ui/<str:name>", webui_views.asset),
    path("api/csrf/", csrf_token),
    path("api/auth/", include("accounts.urls")),
    path("api/schedules/", include("schedules.urls")),
    path("api/tables/", include("tables.urls")),
    path("api/attendance/", include("attendance.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/analytics/", include("analytics.urls")),
]
