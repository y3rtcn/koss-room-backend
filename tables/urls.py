from django.urls import path
from . import views

urlpatterns = [path("", views.tables), path("<str:table_id>/use/", views.use)]
