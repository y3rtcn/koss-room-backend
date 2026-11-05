from django.urls import path

from . import views

urlpatterns = [
    path("", views.schedule_list, name="schedule-list"),
    path("create/", views.schedule_create, name="schedule-create"),
    path("<int:schedule_id>/", views.schedule_detail, name="schedule-detail"),
    path("<int:schedule_id>/update/", views.schedule_update, name="schedule-update"),
    path("<int:schedule_id>/cancel/", views.schedule_cancel, name="schedule-cancel"),
]