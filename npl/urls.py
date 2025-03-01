from django.contrib import admin
from django.urls import include, path

from npl import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path('api/v1/auctions/bid/<str:auctionid>/', views.auction_bid_api),
    path('api/v1/wishlist/bulk/', views.wishlist_bulk),
    path('api/v1/wishlist/interesting/<str:playerid>/', views.interesting_action),
    path('auctions/', views.auction_list),
    path("accounts/", include("django.contrib.auth.urls")),
    path('pages/<str:slug>/', views.npl_page_detail),
    path('pages/', views.npl_page_list),
    path("transactions/", views.transactions),
    path("players/search/", views.search),
    path("players/<str:playerid>/", views.player_detail),
    path("teams/<str:short_name>/", views.team_detail),
    path("teams/my/wishlist/", views.my_wishlist),
    path("", views.index),
]