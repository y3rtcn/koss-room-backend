from django.urls import path
from . import views

urlpatterns = [
    path("", views.schedules),
    path("<str:schedule_id>/", views.detail),
    path("<str:schedule_id>/cancel/", views.cancel),
    path("<str:schedule_id>/recruitment/", views.recruitment),
    path("<str:schedule_id>/participation/", views.participation),
]
