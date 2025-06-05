from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect

from npl import views
from npl import auth

def admin_login_redirect(request):
    """Redirect admin login to our magic link login"""
    return redirect('account_login')

urlpatterns = [
    # Redirect admin login to our magic link login
    path("admin/login/", admin_login_redirect, name='admin_login_redirect'),
    path("admin/", admin.site.urls),
    path('api/v1/auctions/bid/<str:auctionid>/', views.auction_bid_api),
    path('api/v1/auctions/test/', views.auction_test_view),
    path('api/v1/auctions/debug/<int:auction_id>/', views.auction_debug_view),
    path('api/v1/players/<str:playerid>/nominate/', views.nominate_player_api),
    path('api/v1/wishlist/bulk/', views.wishlist_bulk),
    path('api/v1/wishlist/interesting/<str:playerid>/', views.interesting_action),
    path('auctions/', views.auction_list),
    path('auctions/test/', views.auction_test_page),
    path('nominations/', views.nominations_list),
    
    # Authentication URLs - Override allauth login with our custom magic link auth
    path('accounts/login/', auth.login_view, name='account_login'),
    path('auth/magic-link/', auth.magic_link_view, name='magic_link'),
    path('auth/magic-link/verify/<str:token>/', auth.magic_link_verify_view, name='magic_link_verify'),
    path('accounts/', include('allauth.urls')),  # This includes all other django-allauth URLs
    
    path('pages/<str:slug>/', views.npl_page_detail),
    path('pages/', views.npl_page_list),
    
    # Transaction form system
    path("transactions/form/", views.transaction_form_step1, name='transaction_form'),
    path("transactions/form/step2/", views.transaction_form_step2, name='transaction_form_step2'),
    path("transactions/success/", views.transaction_success, name='transaction_success'),
    path("transactions/list/", views.transaction_list, name='transaction_list'),
    path("transactions/", views.transactions),
    
    path("players/search/", views.search),
    path("players/<str:playerid>/", views.player_detail),
    path("teams/<str:short_name>/", views.team_detail),
    path("teams/my/wishlist/", views.my_wishlist),
    path("", views.index, name='index'),
]