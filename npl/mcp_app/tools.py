"""FastMCP tools shared by the HTTPS server and the stdio bridge."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from mcp.server.fastmcp import FastMCP

from npl.mcp_app import filings, services
from npl.mcp_app.context import get_current_owner, require_current_owner


INSTRUCTIONS = (
    "Read-only National Pastime League tools for rosters, cap and cash, "
    "auctions, drafts, trades, and wishlists. list_trades returns the players, "
    "draft picks, and cash each club received, with club names. "
    "list_transactions includes team_name, acquiring_team_name, draft_pick, and cash. "
    "list_pick_inventory is the unused draft picks. list_team_ledger includes "
    "contract payroll_lines plus cash and IFA adjustments. list_free_agents ranks "
    "unowned players by full-season MLB WAR and pages with offset. That WAR is the "
    "whole MLB season, not the portion with one NPL club. npl_lines are the "
    "club-split sim stats. get_player lists the NPL clubs he has been on. "
    "forty_man is the 40-man count (roster_40man, excluding the end-of-season IL "
    "and the foreign list). reserve is the 85-man count (everyone except "
    "end-of-season IL, foreign, and retired). A read-write key files club "
    "moves with create_transaction_proposal: a nontender (non_tender), a trade, "
    "sending a player down (option_minors), calling a player up (recall_option), "
    "a release, an injured-list move, a signing, or a waiver claim. Pass player "
    "as the mlb_id. Omit team when the account owns one club. A trade needs "
    "counterparty, the other club's abbreviation. Draft selections and auction "
    "bids are not on this server. A filing is a proposal. The player stays put "
    "until the league office posts it. agree_transaction, decline_transaction, "
    "and withdraw_transaction answer a proposal. claim_waiver claims an open "
    "waiver and is not an auction bid. A read-only key can look these up and "
    "cannot file. list_transaction_proposals is what has been filed. "
    "list_transactions is the posted ledger."
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


def _http_send(method: str, path: str, body: dict | None = None) -> Any:
    base = (os.environ.get("NPL_API_URL") or "").rstrip("/")
    token = os.environ.get("NPL_API_TOKEN") or ""
    if not base or not token:
        raise RuntimeError("Stdio mode requires NPL_API_URL and NPL_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    kwargs: dict[str, Any] = {"headers": headers}
    if body is not None:
        headers["Content-Type"] = "application/json"
        kwargs["content"] = json.dumps(body).encode()
    with httpx.Client(timeout=60.0) as client:
        response = client.request(method, f"{base}{path}", **kwargs)
    if response.status_code == 401:
        raise RuntimeError("NPL API token rejected (401)")
    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("detail") or ""
        except ValueError:
            detail = response.text
        raise RuntimeError(detail or f"NPL API {response.status_code}")
    if not response.content:
        return {"ok": True}
    return response.json()


def _remote_result(fn) -> str:
    try:
        return _dump(fn())
    except Exception as exc:
        return _dump({"error": str(exc)})


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
        """Roster sections for one club. Omit abbreviation to use your club. WAR is the full MLB season. npl_lines are the club-split sim stats."""
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
        sort: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """Search players. sort is name or war. war ranks by full-season MLB WAR. offset pages past the limit. total is the full match count."""
        data = await sync_to_async(services.search_players)(
            name=name,
            position=position,
            owned=owned,
            team=team,
            level=level,
            roster_40man=roster_40man,
            roster_30man=roster_30man,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def list_free_agents(
        name: str | None = None,
        position: str | None = None,
        level: str | None = None,
        pool: str | None = None,
        season: int | None = None,
        sort: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> str:
        """Unowned players ranked by full-season MLB WAR. That WAR is not split by NPL club. Pass offset for the next page. pool is mlb_current, milb_current, mlb_prior, or milb_prior."""
        data = await sync_to_async(services.list_free_agents)(
            name=name,
            position=position,
            level=level,
            pool=pool,
            season=season,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def get_player(mlb_id: str) -> str:
        """One player: contract, full-season MLB WAR, club-split sim lines, and the NPL clubs he has been on."""
        data = await sync_to_async(services.get_player)(mlb_id)
        return _dump(data)

    @mcp.tool()
    async def list_draft_picks(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        original_team: str | None = None,
        held: str | None = None,
        limit: int = 500,
    ) -> str:
        """List draft picks. season is offseason or midseason. draft_type is open, aa, or balance. held=true is picks no player has been taken with."""
        data = await sync_to_async(services.list_draft_picks)(
            team=team,
            year=year,
            season=season,
            draft_type=draft_type,
            original_team=original_team,
            held=held,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def list_pick_inventory(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        limit: int = 1000,
    ) -> str:
        """Unused draft picks still held by clubs, grouped by club name."""
        data = await sync_to_async(services.list_pick_inventory)(
            team=team,
            year=year,
            season=season,
            draft_type=draft_type,
            limit=limit,
        )
        return _dump(data)

    @mcp.tool()
    async def list_trades(
        team: str | None = None,
        season: int | None = None,
        limit: int = 200,
    ) -> str:
        """List trades. Each deal includes the players, draft picks, and cash each club received, plus club names."""
        data = await sync_to_async(services.list_trades)(team=team, season=season, limit=limit)
        return _dump(data)

    @mcp.tool()
    async def list_transactions(
        team: str | None = None,
        year: int | None = None,
        limit: int = 200,
    ) -> str:
        """List posted ledger rows, including club names, draft-pick text, and cash."""
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
        """Cash and IFA adjustments plus payroll_lines, the contract salary of each player. book is payroll, cash, or ifa. Omit abbreviation for your club."""
        owner = get_current_owner()
        data = await sync_to_async(services.list_team_ledger)(
            abbreviation=abbreviation, owner=owner, year=year, book=book
        )
        return _dump(data)

    _register_filing_tools(mcp, remote=False)


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
        """Roster sections for one club. Omit abbreviation to use your club. WAR is the full MLB season. npl_lines are the club-split sim stats."""
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
        sort: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """Search players. sort is name or war. offset pages past the limit."""
        params = _params(
            {
                "name": name,
                "position": position,
                "owned": owned,
                "team": team,
                "level": level,
                "roster_40man": roster_40man,
                "roster_30man": roster_30man,
                "sort": sort,
                "offset": offset,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/players/search/", params=params))

    @mcp.tool()
    def list_free_agents(
        name: str | None = None,
        position: str | None = None,
        level: str | None = None,
        pool: str | None = None,
        season: int | None = None,
        sort: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> str:
        """Unowned players ranked by full-season MLB WAR. Pass offset for the next page."""
        params = _params(
            {
                "name": name,
                "position": position,
                "level": level,
                "pool": pool,
                "season": season,
                "sort": sort,
                "offset": offset,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/free-agents/", params=params))

    @mcp.tool()
    def get_player(mlb_id: str) -> str:
        """One player: contract, full-season MLB WAR, club-split sim lines, and NPL club stints."""
        return _dump(_http_get(f"/api/mcp/v1/players/{mlb_id}/"))

    @mcp.tool()
    def list_draft_picks(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        original_team: str | None = None,
        held: str | None = None,
        limit: int = 500,
    ) -> str:
        """List draft picks. held=true is picks no player has been taken with."""
        params = _params(
            {
                "team": team,
                "year": year,
                "season": season,
                "draft_type": draft_type,
                "original_team": original_team,
                "held": held,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/draft-picks/", params=params))

    @mcp.tool()
    def list_pick_inventory(
        team: str | None = None,
        year: str | None = None,
        season: str | None = None,
        draft_type: str | None = None,
        limit: int = 1000,
    ) -> str:
        """Unused draft picks still held by clubs, grouped by club name."""
        params = _params(
            {
                "team": team,
                "year": year,
                "season": season,
                "draft_type": draft_type,
                "limit": limit,
            }
        )
        return _dump(_http_get("/api/mcp/v1/pick-inventory/", params=params))

    @mcp.tool()
    def list_trades(team: str | None = None, season: int | None = None, limit: int = 200) -> str:
        """List trades. Each deal includes the players, draft picks, and cash each club received, plus club names."""
        params = _params({"team": team, "season": season, "limit": limit})
        return _dump(_http_get("/api/mcp/v1/trades/", params=params))

    @mcp.tool()
    def list_transactions(team: str | None = None, year: int | None = None, limit: int = 200) -> str:
        """List posted ledger rows, including club names, draft-pick text, and cash."""
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
        """Cash and IFA adjustments plus payroll_lines, the contract salary of each player."""
        params = _params({"year": year, "book": book})
        if abbreviation:
            return _dump(_http_get(f"/api/mcp/v1/teams/{abbreviation}/ledger/", params=params))
        return _dump(_http_get("/api/mcp/v1/ledger/", params=params))

    _register_filing_tools(mcp, remote=True)


def _register_filing_tools(mcp: FastMCP, *, remote: bool) -> None:
    if remote:

        @mcp.tool()
        def list_transaction_kinds() -> str:
            """Codes a club can file. Draft selections and auction bids are not listed."""

            def run():
                payload = _http_get("/api/v1/transactions/kinds/?fileable=1")
                return payload

            return _remote_result(run)

        @mcp.tool()
        def list_transaction_proposals() -> str:
            """Proposals your clubs have filed or been asked to agree to. Not the posted ledger."""
            return _remote_result(lambda: _http_get("/api/v1/transactions/proposals/"))

        @mcp.tool()
        def get_transaction_proposal(proposal_id: int) -> str:
            """One proposal your club is party to, including assets and who still has to agree."""
            return _remote_result(
                lambda: _http_get(f"/api/v1/transactions/proposals/{proposal_id}/")
            )

        @mcp.tool()
        def create_transaction_proposal(
            code: str,
            team: str | int | None = None,
            player: str | int | None = None,
            counterparty: str | int | None = None,
            counterparty_teams: list[str | int] | None = None,
            assets: list[dict[str, Any]] | None = None,
            notes: str | None = None,
            effective_date: str | None = None,
            contract_terms: dict[str, Any] | None = None,
            veteran_disposition: str | None = None,
            amount: int | None = None,
        ) -> str:
            """File a move for the key's owner. code is non_tender, trade, option_minors (send down), recall_option (call up), release, an injured-list code, a signing, or a waiver request. player is the mlb_id for a one-player move. Omit team when the account owns one club; otherwise pass an abbreviation. A trade needs counterparty, the other club's abbreviation. assets lists the pieces of a larger trade; from_team and to_team take an abbreviation or an id. Draft selections and auction bids are refused. This stores a proposal. The player does not move until the league office posts it. Needs a read-write key."""

            def run():
                body = filings.proposal_body(
                    code=code,
                    team=team,
                    player=player,
                    counterparty=counterparty,
                    counterparty_teams=counterparty_teams,
                    assets=assets,
                    notes=notes,
                    effective_date=effective_date,
                    contract_terms=contract_terms,
                    veteran_disposition=veteran_disposition,
                    amount=amount,
                )
                return _http_send("POST", "/api/v1/transactions/proposals/", body)

            return _remote_result(run)

        @mcp.tool()
        def agree_transaction(proposal_id: int) -> str:
            """Agree to a proposal waiting on your club. Needs a read-write key. The player stays put until the league office posts the move."""
            return _remote_result(
                lambda: _http_send("POST", f"/api/v1/transactions/proposals/{proposal_id}/agree/", {})
            )

        @mcp.tool()
        def decline_transaction(proposal_id: int) -> str:
            """Decline a proposal waiting on your club. Needs a read-write key."""
            return _remote_result(
                lambda: _http_send(
                    "POST", f"/api/v1/transactions/proposals/{proposal_id}/decline/", {}
                )
            )

        @mcp.tool()
        def withdraw_transaction(proposal_id: int) -> str:
            """Withdraw a proposal your club filed. Needs a read-write key."""
            return _remote_result(
                lambda: _http_send(
                    "POST", f"/api/v1/transactions/proposals/{proposal_id}/withdraw/", {}
                )
            )

        @mcp.tool()
        def list_open_waivers() -> str:
            """Open waivers a club can claim. This is not an auction."""
            return _remote_result(lambda: _http_get("/api/v1/waivers/"))

        @mcp.tool()
        def claim_waiver(
            waiver_id: int,
            notes: str | None = None,
            team: str | int | None = None,
        ) -> str:
            """Claim a player on an open waiver. This is not an auction bid. Needs a read-write key."""

            def run():
                body = {"notes": notes or ""}
                if team not in (None, ""):
                    body["team"] = team
                return _http_send("POST", f"/api/v1/waivers/{waiver_id}/claim/", body)

            return _remote_result(run)

        return

    @mcp.tool()
    async def list_transaction_kinds() -> str:
        """Codes a club can file, including a nontender, a trade, option_minors (send down), and recall_option (call up). Draft selections and auction bids are not listed."""
        return _dump(filings.list_transaction_kinds())

    @mcp.tool()
    async def list_transaction_proposals() -> str:
        """Proposals your clubs have filed or been asked to agree to. This is not the posted ledger."""
        data = await sync_to_async(filings.list_transaction_proposals)()
        return _dump(data)

    @mcp.tool()
    async def get_transaction_proposal(proposal_id: int) -> str:
        """One proposal your club is party to, including assets and who still has to agree."""
        data = await sync_to_async(filings.get_transaction_proposal)(proposal_id)
        return _dump(data)

    @mcp.tool()
    async def create_transaction_proposal(
        code: str,
        team: str | int | None = None,
        player: str | int | None = None,
        counterparty: str | int | None = None,
        counterparty_teams: list[str | int] | None = None,
        assets: list[dict[str, Any]] | None = None,
        notes: str | None = None,
        effective_date: str | None = None,
        contract_terms: dict[str, Any] | None = None,
        veteran_disposition: str | None = None,
        amount: int | None = None,
    ) -> str:
        """File a move for the key's owner. code is non_tender, trade, option_minors (send down), recall_option (call up), release, an injured-list code, a signing, or a waiver request. player is the mlb_id for a one-player move. Omit team when the account owns one club; otherwise pass an abbreviation. A trade needs counterparty, the other club's abbreviation. assets lists the pieces of a larger trade; from_team and to_team take an abbreviation or an id. Draft selections and auction bids are refused. This stores a proposal. The player does not move until the league office posts it. Needs a read-write key."""
        data = await sync_to_async(filings.create_transaction_proposal)(
            code=code,
            team=team,
            player=player,
            counterparty=counterparty,
            counterparty_teams=counterparty_teams,
            assets=assets,
            notes=notes,
            effective_date=effective_date,
            contract_terms=contract_terms,
            veteran_disposition=veteran_disposition,
            amount=amount,
        )
        return _dump(data)

    @mcp.tool()
    async def agree_transaction(proposal_id: int) -> str:
        """Agree to a proposal waiting on your club. Needs a read-write key. The player stays put until the league office posts the move."""
        data = await sync_to_async(filings.agree_transaction)(proposal_id)
        return _dump(data)

    @mcp.tool()
    async def decline_transaction(proposal_id: int) -> str:
        """Decline a proposal waiting on your club. Needs a read-write key."""
        data = await sync_to_async(filings.decline_transaction)(proposal_id)
        return _dump(data)

    @mcp.tool()
    async def withdraw_transaction(proposal_id: int) -> str:
        """Withdraw a proposal your club filed. Needs a read-write key."""
        data = await sync_to_async(filings.withdraw_transaction)(proposal_id)
        return _dump(data)

    @mcp.tool()
    async def list_open_waivers() -> str:
        """Open waivers a club can claim. This is not an auction."""
        data = await sync_to_async(filings.list_open_waivers)()
        return _dump(data)

    @mcp.tool()
    async def claim_waiver(
        waiver_id: int,
        notes: str | None = None,
        team: str | int | None = None,
    ) -> str:
        """Claim a player on an open waiver. This is not an auction bid. Needs a read-write key."""
        data = await sync_to_async(filings.claim_waiver)(waiver_id, notes=notes or "", team=team)
        return _dump(data)
