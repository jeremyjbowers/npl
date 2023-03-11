from django.contrib import admin
from django.urls import include, path

from npl import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path('auctions/', views.auction_list),
    path("accounts/", include("django.contrib.auth.urls")),
    path('pages/<str:slug>/', views.npl_page_detail),
    path('pages/', views.npl_page_list),
    path("transactions/", views.transactions),
    path("players/search/", views.search),
    path("players/<str:playerid>/", views.player_detail),
    path("teams/<str:nickname>/", views.team_detail),
    path("", views.index),
]