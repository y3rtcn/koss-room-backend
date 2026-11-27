from django.urls import path

from . import views

urlpatterns = [
    path("daily/", views.daily), path("summary/", views.summary),
    path("recommendations/", views.recommendations),
]
