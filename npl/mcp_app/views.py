"""JSON views for the read-only MCP API. Every route requires a bearer key."""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from npl import models
from npl.mcp_app import services
from npl.mcp_app.auth import require_api_token


def _call(fn):
    try:
        return JsonResponse(fn())
    except models.Team.DoesNotExist:
        return JsonResponse({"error": "No team found"}, status=404)


@require_GET
@require_api_token
def season_context(request):
    return JsonResponse(services.get_season_context(owner=request.mcp_owner))


@require_GET
@require_api_token
def teams_list(request):
    return JsonResponse(services.list_teams())


@require_GET
@require_api_token
def my_roster(request):
    return _call(lambda: services.get_team_roster(owner=request.mcp_owner))


@require_GET
@require_api_token
def team_roster(request, abbreviation):
    return _call(lambda: services.get_team_roster(abbreviation=abbreviation, owner=request.mcp_owner))


@require_GET
@require_api_token
def my_compliance(request):
    return _call(lambda: services.get_roster_compliance(owner=request.mcp_owner))


@require_GET
@require_api_token
def team_compliance(request, abbreviation):
    return _call(
        lambda: services.get_roster_compliance(abbreviation=abbreviation, owner=request.mcp_owner)
    )


@require_GET
@require_api_token
def my_ledger(request):
    params = request.GET
    return _call(
        lambda: services.list_team_ledger(
            owner=request.mcp_owner,
            year=params.get("year"),
            book=params.get("book"),
        )
    )


@require_GET
@require_api_token
def team_ledger(request, abbreviation):
    params = request.GET
    return _call(
        lambda: services.list_team_ledger(
            abbreviation=abbreviation,
            owner=request.mcp_owner,
            year=params.get("year"),
            book=params.get("book"),
        )
    )


@require_GET
@require_api_token
def players_search(request):
    params = request.GET
    try:
        payload = services.search_players(
            name=params.get("name"),
            position=params.get("position"),
            owned=params.get("owned"),
            team=params.get("team"),
            level=params.get("level"),
            roster_40man=params.get("roster_40man"),
            roster_30man=params.get("roster_30man"),
            limit=params.get("limit", 100),
        )
    except models.Team.DoesNotExist:
        return JsonResponse({"error": "No team found"}, status=404)
    return JsonResponse(payload)


@require_GET
@require_api_token
def draft_picks(request):
    params = request.GET
    try:
        payload = services.list_draft_picks(
            team=params.get("team"),
            year=params.get("year"),
            season=params.get("season"),
            draft_type=params.get("draft_type"),
            original_team=params.get("original_team"),
            limit=params.get("limit", 500),
        )
    except models.Team.DoesNotExist:
        return JsonResponse({"error": "No team found"}, status=404)
    return JsonResponse(payload)


@require_GET
@require_api_token
def trades_list(request):
    params = request.GET
    try:
        payload = services.list_trades(
            team=params.get("team"),
            season=params.get("season"),
            limit=params.get("limit", 200),
        )
    except models.Team.DoesNotExist:
        return JsonResponse({"error": "No team found"}, status=404)
    return JsonResponse(payload)


@require_GET
@require_api_token
def transactions_list(request):
    params = request.GET
    try:
        payload = services.list_transactions(
            team=params.get("team"),
            year=params.get("year"),
            limit=params.get("limit", 200),
        )
    except models.Team.DoesNotExist:
        return JsonResponse({"error": "No team found"}, status=404)
    return JsonResponse(payload)


@require_GET
@require_api_token
def my_wishlist(request):
    return _call(lambda: services.get_my_wishlist(request.mcp_owner))


@require_GET
@require_api_token
def auctions_list(request):
    return JsonResponse(services.list_auctions(owner=request.mcp_owner))
