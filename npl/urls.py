from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect

from npl import views
from npl import auth
from npl import game_views
from npl.transactions import api as transaction_api
from npl.mcp_app import views as mcp_views
from npl.token_views import api_tokens

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
    path('api/v1/transactions/kinds/', transaction_api.kinds),
    path('api/v1/transactions/proposals/', transaction_api.proposals),
    path('api/v1/transactions/proposals/<int:proposal_id>/', transaction_api.proposal_detail),
    path('api/v1/transactions/proposals/<int:proposal_id>/agree/', transaction_api.proposal_agree),
    path('api/v1/transactions/proposals/<int:proposal_id>/decline/', transaction_api.proposal_decline),
    path('api/v1/transactions/proposals/<int:proposal_id>/withdraw/', transaction_api.proposal_withdraw),
    path('api/v1/waivers/<int:waiver_id>/claim/', transaction_api.waiver_claim),
    path('api/v1/drafts/', transaction_api.drafts),
    path('api/v1/drafts/<int:session_id>/pick/', transaction_api.draft_pick),
    path('api/v1/mcp/tools/', transaction_api.mcp_tools),
    path("api/mcp/v1/season/", mcp_views.season_context),
    path("api/mcp/v1/teams/", mcp_views.teams_list),
    path("api/mcp/v1/roster/", mcp_views.my_roster),
    path("api/mcp/v1/compliance/", mcp_views.my_compliance),
    path("api/mcp/v1/teams/<str:abbreviation>/roster/", mcp_views.team_roster),
    path("api/mcp/v1/teams/<str:abbreviation>/compliance/", mcp_views.team_compliance),
    path("api/mcp/v1/teams/<str:abbreviation>/ledger/", mcp_views.team_ledger),
    path("api/mcp/v1/ledger/", mcp_views.my_ledger),
    path("api/mcp/v1/players/search/", mcp_views.players_search),
    path("api/mcp/v1/draft-picks/", mcp_views.draft_picks),
    path("api/mcp/v1/trades/", mcp_views.trades_list),
    path("api/mcp/v1/transactions/", mcp_views.transactions_list),
    path("api/mcp/v1/wishlist/", mcp_views.my_wishlist),
    path("api/mcp/v1/auctions/", mcp_views.auctions_list),
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
    path("transactions/form/trade-roster/", views.trade_roster, name='trade_roster'),
    path("transactions/form/step2/", views.transaction_form_step2, name='transaction_form_step2'),
    path("transactions/success/", views.transaction_success, name='transaction_success'),
    path("transactions/list/", views.transaction_list, name='transaction_list'),
    path("transactions/proposals/<int:proposal_id>/respond/", views.proposal_respond, name='proposal_respond'),
    path("transactions/proposals/<int:proposal_id>/", views.proposal_detail_page, name='proposal_detail'),
    path("transactions/roundup/", views.roster_roundup_page, name="roster_roundup"),
    path("transactions/audit/", views.transaction_audit_page, name="transaction_audit"),
    path("transactions/trades/", views.transactions, {"mode": "trades"}),
    path("transactions/other/", views.transactions, {"mode": "other"}),
    path("transactions/", views.transactions),
    path("my/api-keys/", api_tokens, name="my_api_keys"),
    path("account/tokens/", api_tokens, name="api_tokens"),
    
    path("players/search/", views.search),
    path("players/<str:playerid>/cards/", game_views.player_cards, name="player_cards"),
    path("players/<str:playerid>/", views.player_detail),
    path("schedule/", game_views.schedule, name="schedule"),
    path("schedule/<int:year>/", game_views.schedule, name="schedule_year"),
    path("leaders/", game_views.leaders, name="leaders"),
    path("leaders/<int:year>/", game_views.leaders, name="leaders_year"),
    path("series/<int:series_id>/", game_views.series_detail, name="series_detail"),
    path("games/<int:game_id>/", game_views.week_game, name="week_game"),
    path("teams/<str:short_name>/lineup/", game_views.lineup, name="team_lineup"),
    path("teams/<str:short_name>/lineup/<int:year>/<int:week>/", game_views.lineup, name="team_lineup_week"),
    path("teams/<str:short_name>/rotation/", game_views.rotation, name="team_rotation"),
    path("teams/<str:short_name>/rotation/<int:year>/<int:week>/", game_views.rotation, name="team_rotation_week"),
    path("teams/<str:short_name>/bullpen/", game_views.bullpen, name="team_bullpen"),
    path("teams/<str:short_name>/bullpen/<int:year>/<int:week>/", game_views.bullpen, name="team_bullpen_week"),
    path("teams/<str:short_name>/bench/", game_views.bench, name="team_bench"),
    path("teams/<str:short_name>/bench/<int:year>/<int:week>/", game_views.bench, name="team_bench_week"),
    path("teams/<str:short_name>/schedule/", game_views.team_schedule, name="team_schedule"),
    path("teams/<str:short_name>/schedule/<int:year>/", game_views.team_schedule, name="team_schedule_year"),
    path("teams/<str:short_name>/stats/", game_views.team_stats, name="team_stats"),
    path("teams/<str:short_name>/stats/<int:year>/", game_views.team_stats, name="team_stats_year"),
    path("teams/<str:short_name>/cards/", game_views.team_cards, name="team_cards"),
    path("teams/<str:short_name>/cards/<int:year>/<int:week>/", game_views.team_cards, name="team_cards_week"),
    path("teams/<str:short_name>/", views.team_detail),
    path("teams/my/wishlist/", views.my_wishlist),
    path("robots.txt", views.robots_txt),
    path("", views.index, name='index'),
]