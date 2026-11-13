from django.urls import path

from . import views

urlpatterns = [
    path("", views.schedule_list, name="schedule-list"),
    path("create/", views.schedule_create, name="schedule-create"),
    path("<int:schedule_id>/", views.schedule_detail, name="schedule-detail"),
    path("<int:schedule_id>/update/", views.schedule_update, name="schedule-update"),
    path("<int:schedule_id>/cancel/", views.schedule_cancel, name="schedule-cancel"),
    path("<int:schedule_id>/join/", views.schedule_join, name="schedule-join"),
    path("<int:schedule_id>/participants/", views.participant_list, name="schedule-participants"),
    path("<int:schedule_id>/leave/", views.schedule_leave, name="schedule-leave"),
]