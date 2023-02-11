from django.contrib import admin
from django.urls import include, path

from npl import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("teams/<str:nickname>/", views.team_detail),
    path("", views.index),
]