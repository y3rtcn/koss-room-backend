from django.urls import path

from . import views

urlpatterns = [
    path("", views.space_list, name="space-list"),
    path("create/", views.space_create, name="space-create"),
]