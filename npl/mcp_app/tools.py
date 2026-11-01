"""FastMCP tools shared by the HTTPS server and the stdio bridge."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from mcp.server.fastmcp import FastMCP

from npl.mcp_app import services
from npl.mcp_app.context import get_current_owner, require_current_owner


INSTRUCTIONS = (
    "Read-only National Pastime League tools for rosters, cap and cash, "
    "auctions, drafts, trades, and wishlists. forty_man is the 40-man count "
    "(roster_40man, excluding the end-of-season IL and the foreign list). "
    "reserve is the 85-man count (everyone except end-of-season IL, foreign, "
    "and retired). This server does not file transactions. Write actions use "
    "the same bearer token on /api/v1/transactions/."
)


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _http_get(path: str, params: dict | None = None) -> Any:
    base = (os.environ.get("NPL_API_URL") or "").rstrip("/")
    token = os.environ.get("NPL_API_TOKEN") or ""
    if not base or not token:
        raise RuntimeError("Stdio mode requires NPL_API_URL and NPL_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60.0) as client:
        response = client.get(f"{base}{path}", params=params or {}, headers=headers)
        if response.status_code == 401:
            raise RuntimeError("NPL API token rejected (401)")
        response.raise_for_status()
        return response.json()


def _params(values: dict) -> dict:
    return {key: value for key, value in values.items() if value is not None and value != ""}


def build_mcp(*, mode: str = "local") -> FastMCP:
    """mode=local uses the Django ORM. mode=remote calls NPL_API_URL."""
    mcp = FastMCP("npl", instructions=INSTRUCTIONS)
    if mode == "remote":
        _register_remote_tools(mcp)
    else:
        _register_local_tools(mcp)
    return mcp


def _register_local_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_season_context() -> str:
        """Current NPL season, phase, cap, and the authenticated owner's team."""
        owner = get_current_owner()
        data = await sync_to_async(services.get_season_context)(owner=owner)
        return _dump(data)

    @mcp.tool()
    async def list_teams() -> str:
        """List NPL clubs with division, payroll, cap space, cash, and IFA pool."""
        data = await sync_to_async(services.list_teams)()
        return _dump(data)

    @mcp.tool()
    async def get_team_roster(abbreviation: str | None = None) -> str:
        """Roster sections for one club. Omit abbreviation to use your club."""
        owner = get_current_owner()
        data = await sync_to_async(services.get_team_roster)(abbreviation=abbreviation, owner=owner)
        return _dump(data)

    @mcp.tool()
    async def get_roster_compliance(abbreviation: str | None = None) -> str:
        """40-man and 85-man counts against the roster limits, plus any warnings."""
        owner = get_current_owner()
        data = await sync_to_async(services.get_roster_compliance)(
            abbreviation=abbreviation, owner=owner
        )
        return _dump(data)

    @mcp.tool()
    async def search_players(
        name: str | None = None,
        position: str | None = None,
        owned: str | None = None,
        team: str | None = None,
        level: str | None = None,
        roster_40man: str | None = None,
        roster_30man: str | None = None,
        limit: int = 100,
    ) -> str:
        """Search players by name, position (or h/p), owned, club, level, and roster flags."""
        data = await sync_to_async(services.search_players)(
            name=name,
            position=position,
            owned=owned,
            team=team,
            level=level,
            roster_40man=roster_40man,
            roster_30man=roster_30man,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def list_draft_picks(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        original_team: str | None = None,
        limit: int = 500,
    ) -> str:
        """List draft picks. season is offseason or midseason. draft_type is open, aa, or balance."""
        data = await sync_to_async(services.list_draft_picks)(
            team=team,
            year=year,
            season=season,
            draft_type=draft_type,
            original_team=original_team,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def list_trades(
        team: str | None = None,
        season: int | None = None,
        limit: int = 200,
    ) -> str:
        """List trades, including the players and picks on each side."""
        data = await sync_to_async(services.list_trades)(team=team, season=season, limit=limit)
        return _dump(data)

    @mcp.tool()
    async def list_transactions(
        team: str | None = None,
        year: int | None = None,
        limit: int = 200,
    ) -> str:
        """List posted ledger transactions for a club or a calendar year."""
        data = await sync_to_async(services.list_transactions)(team=team, year=year, limit=limit)
        return _dump(data)

    @mcp.tool()
    async def get_my_wishlist() -> str:
        """Your club's wishlist, with rank, tier, notes, and tags."""
        owner = require_current_owner()
        data = await sync_to_async(services.get_my_wishlist)(owner)
        return _dump(data)

    @mcp.tool()
    async def list_auctions() -> str:
        """Open auctions. Bid amounts of other clubs stay hidden. my_bid is your club's bid."""
        owner = get_current_owner()
        data = await sync_to_async(services.list_auctions)(owner=owner)
        return _dump(data)

    @mcp.tool()
    async def list_team_ledger(
        abbreviation: str | None = None,
        year: int | None = None,
        book: str | None = None,
    ) -> str:
        """Payroll, cash, and IFA ledger lines. book is payroll, cash, or ifa. Omit abbreviation for your club."""
        owner = get_current_owner()
        data = await sync_to_async(services.list_team_ledger)(
            abbreviation=abbreviation, owner=owner, year=year, book=book
        )
        return _dump(data)


def _register_remote_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_season_context() -> str:
        """Current NPL season, phase, cap, and the authenticated owner's team."""
        return _dump(_http_get("/api/mcp/v1/season/"))

    @mcp.tool()
    def list_teams() -> str:
        """List NPL clubs with division, payroll, cap space, cash, and IFA pool."""
        return _dump(_http_get("/api/mcp/v1/teams/"))

    @mcp.tool()
    def get_team_roster(abbreviation: str | None = None) -> str:
        """Roster sections for one club. Omit abbreviation to use your club."""
        if abbreviation:
            return _dump(_http_get(f"/api/mcp/v1/teams/{abbreviation}/roster/"))
        return _dump(_http_get("/api/mcp/v1/roster/"))

    @mcp.tool()
    def get_roster_compliance(abbreviation: str | None = None) -> str:
        """40-man and 85-man counts against the roster limits."""
        if abbreviation:
            return _dump(_http_get(f"/api/mcp/v1/teams/{abbreviation}/compliance/"))
        return _dump(_http_get("/api/mcp/v1/compliance/"))

    @mcp.tool()
    def search_players(
        name: str | None = None,
        position: str | None = None,
        owned: str | None = None,
        team: str | None = None,
        level: str | None = None,
        roster_40man: str | None = None,
        roster_30man: str | None = None,
        limit: int = 100,
    ) -> str:
        """Search players by name, position, owned, club, level, and roster flags."""
        params = _params(
            {
                "name": name,
                "position": position,
                "owned": owned,
                "team": team,
                "level": level,
                "roster_40man": roster_40man,
                "roster_30man": roster_30man,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/players/search/", params=params))

    @mcp.tool()
    def list_draft_picks(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        original_team: str | None = None,
        limit: int = 500,
    ) -> str:
        """List draft picks."""
        params = _params(
            {
                "team": team,
                "year": year,
                "season": season,
                "draft_type": draft_type,
                "original_team": original_team,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/draft-picks/", params=params))

    @mcp.tool()
    def list_trades(team: str | None = None, season: int | None = None, limit: int = 200) -> str:
        """List trades, including the players and picks on each side."""
        params = _params({"team": team, "season": season, "limit": limit})
        return _dump(_http_get("/api/mcp/v1/trades/", params=params))

    @mcp.tool()
    def list_transactions(team: str | None = None, year: int | None = None, limit: int = 200) -> str:
        """List posted ledger transactions."""
        params = _params({"team": team, "year": year, "limit": limit})
        return _dump(_http_get("/api/mcp/v1/transactions/", params=params))

    @mcp.tool()
    def get_my_wishlist() -> str:
        """Your club's wishlist, with rank, tier, notes, and tags."""
        return _dump(_http_get("/api/mcp/v1/wishlist/"))

    @mcp.tool()
    def list_auctions() -> str:
        """Open auctions. Other clubs' bid amounts stay hidden."""
        return _dump(_http_get("/api/mcp/v1/auctions/"))

    @mcp.tool()
    def list_team_ledger(
        abbreviation: str | None = None,
        year: int | None = None,
        book: str | None = None,
    ) -> str:
        """Payroll, cash, and IFA ledger lines for a club."""
        params = _params({"year": year, "book": book})
        if abbreviation:
            return _dump(_http_get(f"/api/mcp/v1/teams/{abbreviation}/ledger/", params=params))
        return _dump(_http_get("/api/mcp/v1/ledger/", params=params))
