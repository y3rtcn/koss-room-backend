from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.me),
    path("occupancy/", views.occupancy),
    path("check-in/", views.check_in),
    path("check-out/", views.check_out),
]
