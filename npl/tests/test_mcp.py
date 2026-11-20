"""API keys, the MCP JSON API, club filings, and the Streamable HTTP server."""

import datetime
import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from httpx import ASGITransport, AsyncClient

from npl import models
from npl.api_tokens import generate_token
from npl.mcp_app import filings
from npl.mcp_app.context import reset_current_token, set_current_token
from npl.mcp_app.http_app import create_mcp_http_app, create_site_asgi_application

User = get_user_model()

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "claude", "version": "1"},
    },
}
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


async def _site_login_redirect(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [(b"location", b"/accounts/login/")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


class ApiKeyPageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="keys@example.com", password="secret")
        self.owner = models.Owner.objects.create(
            name="Key Owner", email="keys@example.com", user=self.user
        )
        self.team = models.Team.objects.create(
            full_name="Key Club", short_name="Key", abbreviation="KEY"
        )
        self.team.owners.add(self.owner)
        self.other = User.objects.create_user(email="other-keys@example.com", password="secret")
        self.other_owner = models.Owner.objects.create(
            name="Other Keys", email="other-keys@example.com", user=self.other
        )

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get("/my/api-keys/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_owner_generates_sees_and_revokes_a_key(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/my/api-keys/",
            {"action": "create", "scope": "read", "name": "lookup"},
            follow=True,
        )
        self.assertEqual(created.status_code, 200)
        token = models.ApiToken.objects.get(user=self.user, name="lookup")
        self.assertEqual(token.token_secret, created.context["tokens"][0].token_secret)
        self.assertTrue(token.token_secret.startswith("npl_"))
        self.assertContains(created, token.token_secret)
        self.assertContains(created, "Read")

        again = self.client.get("/my/api-keys/")
        self.assertContains(again, token.token_secret)

        self.client.logout()
        self.client.force_login(self.other)
        hidden = self.client.get("/my/api-keys/")
        self.assertNotContains(hidden, token.token_secret)
        stolen = self.client.post(
            "/my/api-keys/",
            {"action": "revoke", "token_id": token.id},
        )
        self.assertEqual(stolen.status_code, 404)

        self.client.logout()
        self.client.force_login(self.user)
        revoked = self.client.post(
            "/my/api-keys/",
            {"action": "revoke", "token_id": token.id},
            follow=True,
        )
        self.assertContains(revoked, "Revoked")
        self.assertContains(revoked, token.token_secret)
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)
        self.assertFalse(token.active)
        from npl.api_tokens import authenticate

        self.assertIsNone(authenticate(token.token_secret))

    def test_invalid_scope_does_not_create_a_key(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/my/api-keys/",
            {"action": "create", "scope": "admin", "name": "nope"},
            follow=True,
        )
        self.assertContains(response, "Pick a read or read-write key.")
        self.assertFalse(models.ApiToken.objects.filter(user=self.user).exists())

    def test_user_without_owner_cannot_mint_a_key(self):
        spectator = User.objects.create_user(email="spectator@example.com", password="secret")
        self.client.force_login(spectator)
        page = self.client.get("/my/api-keys/")
        self.assertContains(page, "not linked to an owner")
        denied = self.client.post(
            "/my/api-keys/",
            {"action": "create", "scope": "read", "name": "nope"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(models.ApiToken.objects.filter(user=spectator).exists())

    def test_csrf_is_required_to_mint_a_key(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        blocked = client.post(
            "/my/api-keys/",
            {"action": "create", "scope": "read", "name": "csrf"},
        )
        self.assertEqual(blocked.status_code, 403)
        page = client.get("/my/api-keys/")
        csrf = client.cookies["csrftoken"].value
        created = client.post(
            "/my/api-keys/",
            {
                "action": "create",
                "scope": "read",
                "name": "csrf",
                "csrfmiddlewaretoken": csrf,
            },
            follow=True,
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(models.ApiToken.objects.filter(user=self.user, name="csrf").exists())
        self.assertContains(page, "API keys")

    def test_page_lists_the_mcp_tools(self):
        self.client.force_login(self.user)
        page = self.client.get("/my/api-keys/")
        self.assertContains(page, "What the key reaches")
        self.assertContains(page, "get_season_context")
        self.assertContains(page, "GET /api/mcp/v1/season/")
        self.assertContains(page, "list_free_agents")
        self.assertContains(page, "create_transaction_proposal")
        self.assertContains(page, "option_minors")
        self.assertContains(page, "claim_waiver")
        self.assertContains(page, "Draft selections and auction bids stay off this key.")
        self.assertNotContains(page, "make draft picks")
        self.assertContains(page, page.context["mcp_url"])

    def test_command_mints_a_key_for_an_owner(self):
        out = StringIO()
        call_command(
            "create_owner_api_token",
            "--email",
            "keys@example.com",
            "--label",
            "cli",
            "--scope",
            "read_write",
            stdout=out,
        )
        token = models.ApiToken.objects.get(user=self.user, name="cli")
        self.assertEqual(token.scope, models.ApiToken.READ_WRITE)
        self.assertIn(token.token_secret, out.getvalue())
        from npl.api_tokens import authenticate

        self.assertEqual(authenticate(token.token_secret).pk, token.pk)


class McpReadApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="mcp@example.com", password="secret")
        self.owner = models.Owner.objects.create(
            name="MCP Owner", email="mcp@example.com", user=self.user
        )
        self.team = models.Team.objects.create(
            full_name="MCP Club", short_name="Mcp", abbreviation="MCP"
        )
        self.team.owners.add(self.owner)
        self.other_team = models.Team.objects.create(
            full_name="Other Club", short_name="Oth", abbreviation="OTH"
        )
        self.player = models.Player.objects.create(
            mlb_id="200001",
            name="Ada Player",
            first_name="Ada",
            last_name="Player",
            team=self.team,
            is_owned=True,
            simple_position="SS",
            roster_40man=True,
            roster_30man=True,
        )
        models.Player.objects.create(
            mlb_id="200002",
            name="Bea Free",
            first_name="Bea",
            last_name="Free",
            is_owned=False,
            simple_position="P",
        )
        models.PlayerStatSeason.objects.create(
            player=self.player,
            season=2026,
            hit_stats={"hr": 9, "pa": 100},
        )
        models.Season.objects.create(
            year=2026,
            is_current=True,
            phase=models.Season.REGULAR,
            salary_cap=220,
        )
        models.DraftPick.objects.create(
            draft_type="open",
            year="2026",
            season="offseason",
            draft_round=1,
            pick_number=4,
            team=self.team,
        )
        trade = models.Trade.objects.create(
            date=datetime.date(2026, 3, 2),
            trade_summary="MCP and OTH swap a player",
        )
        trade.teams.add(self.team, self.other_team)
        models.TradeReceipt.objects.create(trade=trade, team=self.team)
        models.Transaction.objects.create(
            date=datetime.date(2026, 4, 1),
            team=self.team,
            player=self.player,
            raw_player="Ada Player",
            raw_transaction_type="Activation",
        )
        wishlist = models.Wishlist.objects.create(team=self.team)
        models.WishlistPlayer.objects.create(
            wishlist=wishlist, player=self.player, rank=1, tier=2, note="need her"
        )
        self.auction = models.Auction.objects.create(
            player=self.player,
            closes=timezone.now() + datetime.timedelta(days=2),
            min_bid=1,
        )
        models.MLBAuctionBid.objects.create(team=self.team, auction=self.auction, max_bid=6)
        rival_owner = models.Owner.objects.create(name="Rival")
        rival = models.Team.objects.create(
            full_name="Rival Club", short_name="Riv", abbreviation="RIV"
        )
        rival.owners.add(rival_owner)
        models.MLBAuctionBid.objects.create(team=rival, auction=self.auction, max_bid=77)
        models.ClubLedgerEntry.objects.create(
            team=self.team, year=2026, book="cash", label="Trade cash", amount=125000
        )
        _token, self.raw = generate_token(self.user, "agent", "read")

    def _get(self, path, token=None):
        headers = {}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.client.get(path, **headers)

    def test_season_requires_a_token_and_returns_the_club(self):
        self.assertEqual(self._get("/api/mcp/v1/season/").status_code, 401)
        response = self._get("/api/mcp/v1/season/", self.raw)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["year"], 2026)
        self.assertEqual(payload["phase"], "regular")
        self.assertEqual(payload["salary_cap"], 220)
        self.assertEqual(payload["my_team"]["abbreviation"], "MCP")
        self.assertEqual(payload["my_owner"]["email"], "mcp@example.com")

    def test_header_alias_and_revoked_key(self):
        alias = self.client.get("/api/mcp/v1/teams/", HTTP_X_NPL_TOKEN=self.raw)
        self.assertEqual(alias.status_code, 200)
        abbreviations = {team["abbreviation"] for team in alias.json()["teams"]}
        self.assertIn("MCP", abbreviations)

        token = self.user.api_tokens.get()
        from npl.api_tokens import revoke

        revoke(token)
        rejected = self._get("/api/mcp/v1/season/", self.raw)
        self.assertEqual(rejected.status_code, 401)

    def test_roster_search_wishlist_auctions_and_books(self):
        roster = self._get("/api/mcp/v1/roster/", self.raw)
        self.assertEqual(roster.status_code, 200)
        self.assertEqual(roster.json()["counts"]["forty_man"], 1)
        self.assertEqual(roster.json()["team"]["abbreviation"], "MCP")

        missing = self._get("/api/mcp/v1/teams/NOPE/roster/", self.raw)
        self.assertEqual(missing.status_code, 404)

        found = self._get("/api/mcp/v1/players/search/?name=Ada", self.raw)
        self.assertEqual(found.status_code, 200)
        player = found.json()["players"][0]
        self.assertEqual(player["mlb_id"], "200001")
        self.assertEqual(player["stats"]["hit"]["hr"], 9)

        free_agents = self._get("/api/mcp/v1/players/search/?owned=false", self.raw)
        names = {item["name"] for item in free_agents.json()["players"]}
        self.assertEqual(names, {"Bea Free"})

        picks = self._get("/api/mcp/v1/draft-picks/?team=MCP&year=2026", self.raw)
        self.assertEqual(picks.json()["picks"][0]["pick_number"], 4)

        trades = self._get("/api/mcp/v1/trades/?team=MCP", self.raw)
        self.assertEqual(trades.json()["count"], 1)
        self.assertIn("MCP", trades.json()["trades"][0]["teams"])

        ledger_rows = self._get("/api/mcp/v1/transactions/?team=MCP&year=2026", self.raw)
        self.assertEqual(ledger_rows.json()["transactions"][0]["player"], "Ada Player")

        wishlist = self._get("/api/mcp/v1/wishlist/", self.raw)
        self.assertEqual(wishlist.json()["players"][0]["note"], "need her")
        self.assertEqual(wishlist.json()["players"][0]["rank"], 1)

        auctions = self._get("/api/mcp/v1/auctions/", self.raw)
        body = auctions.json()["auctions"][0]
        self.assertEqual(body["my_bid"], 6)
        self.assertTrue(body["has_bids"])
        # Blind auctions publish my_bid only. Other clubs' amounts stay hidden.
        self.assertNotIn(77, body.values())
        self.assertNotIn("amount", body)
        self.assertNotIn("bids", body)

        books = self._get("/api/mcp/v1/ledger/?year=2026", self.raw)
        self.assertEqual(books.json()["entries"][0]["amount"], 125000)

        compliance = self._get("/api/mcp/v1/compliance/", self.raw)
        self.assertTrue(compliance.json()["limits"]["forty_man_ok"])
        self.assertTrue(compliance.json()["limits"]["reserve_ok"])

    def test_trades_include_players_picks_cash_and_club_names(self):
        trade = models.Trade.objects.create(date=datetime.date(2026, 7, 4))
        trade.teams.add(self.team, self.other_team)
        models.Transaction.objects.create(
            date=datetime.date(2026, 7, 4),
            team=self.team,
            acquiring_team=self.other_team,
            player=self.player,
            raw_player="Ada Player",
            raw_transaction_type="Trade",
            trade=trade,
        )
        models.Transaction.objects.create(
            date=datetime.date(2026, 7, 4),
            team=self.other_team,
            acquiring_team=self.team,
            raw_player="Draft Pick",
            raw_draft_pick="2027 open round 1",
            cash_considerations=250000,
            raw_transaction_type="Trade",
            trade=trade,
        )
        body = self._get("/api/mcp/v1/trades/?team=MCP", self.raw).json()
        deal = next(item for item in body["trades"] if item["date"] == "2026-07-04")
        received = {side["team_name"]: side for side in deal["sides"]}
        self.assertEqual(received["Oth"]["players"][0]["name"], "Ada Player")
        self.assertEqual(received["Mcp"]["picks"][0]["description"], "2027 open round 1")
        self.assertEqual(received["Mcp"]["cash"], [250000])
        self.assertEqual({club["name"] for club in deal["clubs"]}, {"Mcp", "Oth"})
        self.assertIn("Ada Player", deal["summary"])

    def test_unlinked_ledger_lines_still_form_a_trade(self):
        models.Team.objects.create(
            full_name="Cheesequake Cheddar",
            short_name="Cheddar",
            abbreviation="CHED",
            tab_id="Cheddar #1",
        )
        models.Team.objects.create(
            full_name="Honolulu Hitmen",
            short_name="Hitmen",
            abbreviation="HIT",
            tab_id="Hitmen #14",
        )
        models.Transaction.objects.create(
            date=datetime.date(2024, 6, 2),
            raw_team="Nose Pickers",
            raw_acquiring_team="Hitmen",
            raw_player="Ada Player",
            player=self.player,
            raw_transaction_type="Trade",
        )
        models.Transaction.objects.create(
            date=datetime.date(2024, 6, 2),
            raw_team="Honolulu Hitmen",
            raw_acquiring_team="Cheesequake Cheddar",
            raw_player="Draft Pick",
            raw_draft_pick="2026 OP3",
            raw_transaction_type="Trade",
        )
        models.Transaction.objects.filter(date=datetime.date(2024, 6, 2)).update(
            team=None, acquiring_team=None
        )
        body = self._get("/api/mcp/v1/trades/?team=CHED&season=2024", self.raw).json()
        self.assertEqual(body["count"], 1)
        deal = body["trades"][0]
        self.assertIsNone(deal["id"])
        received = {side["team_name"]: side for side in deal["sides"]}
        self.assertEqual(received["Hitmen"]["players"][0]["name"], "Ada Player")
        self.assertEqual(received["Cheddar"]["picks"][0]["description"], "2026 OP3")

    def test_transaction_names_resolve_older_club_labels(self):
        models.Team.objects.create(
            full_name="Cheesequake Cheddar",
            short_name="Cheddar",
            abbreviation="CHED",
            tab_id="Cheddar #1",
        )
        models.Transaction.objects.create(
            date=datetime.date(2024, 5, 1),
            raw_team="Nose Pickers",
            raw_player="Ada Player",
            player=self.player,
            raw_transaction_type="Release",
            cash_considerations=750000,
        )
        models.Transaction.objects.filter(date=datetime.date(2024, 5, 1)).update(team=None)
        body = self._get("/api/mcp/v1/transactions/?team=CHED&year=2024", self.raw).json()
        row = body["transactions"][0]
        self.assertEqual(row["team"], "CHED")
        self.assertEqual(row["team_name"], "Cheddar")
        self.assertEqual(row["cash"], 750000)
        self.assertEqual(body["total"], 1)

    def test_pick_inventory_is_the_unused_picks(self):
        models.DraftPick.objects.create(
            draft_type="open",
            year="2026",
            season="offseason",
            draft_round=1,
            pick_number=9,
            team=self.team,
            player=self.player,
        )
        body = self._get("/api/mcp/v1/pick-inventory/?team=MCP&year=2026", self.raw).json()
        numbers = [pick["pick_number"] for pick in body["picks"]]
        self.assertEqual(numbers, [4])
        self.assertEqual(body["clubs"][0]["team_name"], "Mcp")
        self.assertTrue(body["picks"][0]["held"])

    def test_ledger_includes_contract_payroll_lines(self):
        contract = models.Contract.objects.create(
            team=self.team, player=self.player, total_years=1, total_amount=4000000
        )
        models.ContractYear.objects.create(contract=contract, year=2026, amount=4000000)
        body = self._get("/api/mcp/v1/ledger/?year=2026", self.raw).json()
        self.assertEqual(body["entries"][0]["amount"], 125000)
        line = body["payroll_lines"][0]
        self.assertEqual(line["player"], "Ada Player")
        self.assertEqual(line["amount"], 4000000)
        self.assertEqual(line["year"], 2026)

    def test_free_agents_are_ranked_by_full_season_war(self):
        ace = models.Player.objects.create(
            mlb_id="200010",
            name="Zoe Ace",
            first_name="Zoe",
            last_name="Ace",
            is_owned=False,
            simple_position="P",
        )
        models.Player.objects.create(
            mlb_id="200011",
            name="Amy Zee",
            first_name="Amy",
            last_name="Zee",
            is_owned=False,
            simple_position="OF",
        )
        models.PlayerStatSeason.objects.create(
            player=ace,
            season=2026,
            classification="1-MLB",
            level="MLB",
            is_mlb=True,
            hit_stats={"WAR": 6.5, "pa": 400},
        )
        models.PlayerStatSeason.objects.create(
            player=ace,
            season=2026,
            classification="npl",
            level="NPL",
            team=self.team,
            hit_stats={"hr": 2, "pa": 20},
        )
        models.PlayerStatSeason.objects.create(
            player_id="200011",
            season=2026,
            classification="1-MLB",
            level="MLB",
            is_mlb=True,
            hit_stats={"WAR": 0.2, "pa": 50},
        )
        body = self._get("/api/mcp/v1/free-agents/?limit=10", self.raw).json()
        names = [player["name"] for player in body["players"]]
        self.assertEqual(names[0], "Zoe Ace")
        self.assertLess(names.index("Zoe Ace"), names.index("Amy Zee"))
        self.assertLess(names.index("Amy Zee"), names.index("Bea Free"))
        self.assertEqual(body["players"][0]["war"], 6.5)
        self.assertEqual(body["players"][0]["war_scope"], "mlb_season")
        self.assertIn("not split by NPL club", body["players"][0]["war_note"])
        self.assertEqual(body["players"][0]["npl_lines"][0]["team"], "MCP")
        self.assertIsNone(body["players"][0]["npl_lines"][0]["war"])
        self.assertEqual(body["total"], 3)
        page = self._get("/api/mcp/v1/free-agents/?limit=1&offset=1", self.raw).json()
        self.assertEqual(page["players"][0]["name"], "Amy Zee")
        self.assertEqual(page["total"], 3)

    def test_player_detail_lists_club_stints_without_splitting_war(self):
        self.player.team = self.other_team
        self.player.save(update_fields=["team"])
        models.Transaction.objects.create(
            date=datetime.date(2026, 6, 15),
            team=self.team,
            acquiring_team=self.other_team,
            player=self.player,
            raw_player="Ada Player",
            raw_transaction_type="Trade",
        )
        body = self._get("/api/mcp/v1/players/200001/", self.raw).json()
        self.assertEqual(body["stints"][0]["team_name"], "Mcp")
        self.assertEqual(body["stints"][0]["end"], "2026-06-15")
        self.assertEqual(body["stints"][1]["team_name"], "Oth")
        self.assertTrue(body["stints"][1]["current"])
        self.assertIsNone(body["stints"][1]["end"])
        self.assertIn("not divided", body["stint_note"])
        missing = self._get("/api/mcp/v1/players/missing/", self.raw)
        self.assertEqual(missing.status_code, 404)


@override_settings(ALLOWED_HOSTS=["*"])
class MCPHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="http@example.com", password="secret")
        self.owner = models.Owner.objects.create(
            name="HTTP Owner", email="http@example.com", user=self.user
        )
        _token, self.raw = generate_token(self.user, "http", "read")
        _write, self.write_raw = generate_token(self.user, "http-write", "read_write")
        self.team = models.Team.objects.create(
            full_name="HTTP Club", short_name="HTTP", abbreviation="HTP"
        )
        self.team.owners.add(self.owner)
        self.player = models.Player.objects.create(
            mlb_id="900001", name="HTTP Player", team=self.team
        )
        self.app = create_mcp_http_app()
        self.site = create_site_asgi_application(_site_login_redirect)

    async def test_health_requires_a_bearer_token(self):
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/health")
            self.assertEqual(denied.status_code, 401)
            allowed = await client.get("/health", headers={"Authorization": f"Bearer {self.raw}"})
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.json()["service"], "npl-mcp")
            self.assertEqual(allowed.json()["auth"], "bearer")
            self.assertEqual(allowed.json()["transport"], "streamable-http")

    async def test_slashless_mcp_initialize(self):
        transport = ASGITransport(app=self.site)
        async with self.site.router.lifespan_context(self.site):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                bare = await client.post("/mcp", headers=_MCP_HEADERS, json=_INITIALIZE)
                self.assertEqual(bare.status_code, 401)
                self.assertEqual(bare.json()["error"], "Unauthorized")
                self.assertNotIn("location", bare.headers)

                other = await client.get("/teams/")
                self.assertEqual(other.status_code, 302)
                self.assertEqual(other.headers["location"], "/accounts/login/")

                headers = {**_MCP_HEADERS, "Authorization": f"Bearer {self.raw}"}
                ready = await client.post("/mcp", headers=headers, json=_INITIALIZE)
                self.assertEqual(ready.status_code, 200, ready.text)
                body = ready.json()
                self.assertEqual(body["jsonrpc"], "2.0")
                self.assertEqual(body["result"]["serverInfo"]["name"], "npl")

                listed = await client.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                )
                self.assertEqual(listed.status_code, 200, listed.text)
                names = {tool["name"] for tool in listed.json()["result"]["tools"]}
                self.assertIn("get_season_context", names)
                self.assertIn("list_auctions", names)
                self.assertIn("get_my_wishlist", names)
                self.assertIn("list_free_agents", names)
                self.assertIn("list_pick_inventory", names)
                self.assertIn("get_player", names)
                self.assertIn("create_transaction_proposal", names)
                create = next(
                    tool
                    for tool in listed.json()["result"]["tools"]
                    if tool["name"] == "create_transaction_proposal"
                )
                self.assertIn("does not move", create["description"])
                self.assertIn("agree_transaction", names)
                self.assertIn("claim_waiver", names)
                self.assertIn("list_open_waivers", names)
                self.assertNotIn("submit_draft_pick", names)
                self.assertNotIn("list_drafts", names)

    async def test_a_read_key_cannot_file_and_a_write_key_can(self):
        transport = ASGITransport(app=self.site)
        async with self.site.router.lifespan_context(self.site):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                read_headers = {**_MCP_HEADERS, "Authorization": f"Bearer {self.raw}"}
                ready = await client.post("/mcp", headers=read_headers, json=_INITIALIZE)
                self.assertEqual(ready.status_code, 200, ready.text)
                denied = await client.post(
                    "/mcp",
                    headers=read_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "create_transaction_proposal",
                            "arguments": {"code": "release", "player": self.player.mlb_id},
                        },
                    },
                )
                self.assertEqual(denied.status_code, 200, denied.text)
                self.assertIn("read-only", denied.text)

                write_headers = {**_MCP_HEADERS, "Authorization": f"Bearer {self.write_raw}"}
                ready = await client.post("/mcp", headers=write_headers, json=_INITIALIZE)
                self.assertEqual(ready.status_code, 200, ready.text)
                filed = await client.post(
                    "/mcp",
                    headers=write_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "create_transaction_proposal",
                            "arguments": {"code": "release", "player": self.player.mlb_id},
                        },
                    },
                )
                self.assertEqual(filed.status_code, 200, filed.text)
                self.assertIn("proposed", filed.text)
                self.assertIn("release", filed.text)

                blocked = await client.post(
                    "/mcp",
                    headers=write_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {
                            "name": "create_transaction_proposal",
                            "arguments": {"code": "rule4_draft", "player": self.player.mlb_id},
                        },
                    },
                )
                self.assertEqual(blocked.status_code, 200, blocked.text)
                self.assertIn("Draft", blocked.text)

        def still_on_the_club():
            self.player.refresh_from_db()
            return self.player.team_id

        from asgiref.sync import sync_to_async

        self.assertEqual(await sync_to_async(still_on_the_club)(), self.team.id)


class McpFilingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="file@example.com", password="secret")
        self.owner = models.Owner.objects.create(name="Filer", user=self.user)
        self.team = models.Team.objects.create(
            full_name="Nose Pickers", short_name="Pickers", abbreviation="MCP"
        )
        self.team.owners.add(self.owner)
        self.player = models.Player.objects.create(
            mlb_id="424242",
            name="Filing Player",
            team=self.team,
            roster_40man=True,
            options=2,
        )
        self.read_token, self.read_raw = generate_token(self.user, "read", "read")
        self.write_token, self.write_raw = generate_token(self.user, "write", "read_write")
        self.client = Client()

    def _call(self, token, fn, *args, **kwargs):
        reset = set_current_token(token)
        try:
            return fn(*args, **kwargs)
        finally:
            reset_current_token(reset)

    def test_kinds_leave_out_drafts_and_bids(self):
        codes = {kind["code"] for kind in filings.list_transaction_kinds()["kinds"]}
        self.assertIn("non_tender", codes)
        self.assertIn("trade", codes)
        self.assertIn("option_minors", codes)
        self.assertIn("recall_option", codes)
        self.assertNotIn("rule4_draft", codes)
        self.assertNotIn("rule5_draft", codes)
        self.assertNotIn("auction_result", codes)

    def test_a_read_key_cannot_file(self):
        result = self._call(
            self.read_token,
            filings.create_transaction_proposal,
            code="release",
            player=self.player.mlb_id,
        )
        self.assertIn("read-only", result["error"])
        self.assertFalse(models.TransactionProposal.objects.exists())

    def test_nontender_can_be_filed_and_withdrawn(self):
        models.Season.objects.create(year=2026, phase=models.Season.OFFSEASON, is_current=True)
        filed = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="non_tender",
            player=self.player.mlb_id,
        )
        self.assertEqual(filed["kind"], "non_tender", filed)
        self.assertEqual(filed["status"], "proposed")
        self.assertEqual(filed["source"], "api")
        withdrawn = self._call(self.write_token, filings.withdraw_transaction, filed["id"])
        self.assertEqual(withdrawn["status"], "withdrawn", withdrawn)
        self.player.refresh_from_db()
        self.assertEqual(self.player.team_id, self.team.id)

    def test_a_trade_can_be_agreed_without_moving_the_player(self):
        other_user = User.objects.create_user(email="other-file@example.com", password="secret")
        other_owner = models.Owner.objects.create(name="Other", user=other_user)
        other = models.Team.objects.create(
            full_name="Other Club", short_name="Other", abbreviation="OTH"
        )
        other.owners.add(other_owner)
        other_token, _raw = generate_token(other_user, "other", "read_write")

        filed = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="trade",
            player=self.player.mlb_id,
            counterparty="oth",
        )
        self.assertEqual(filed["status"], "awaiting_agreement", filed)
        agreed = self._call(other_token, filings.agree_transaction, filed["id"])
        self.assertEqual(agreed["status"], "agreed", agreed)
        self.player.refresh_from_db()
        self.assertEqual(self.player.team_id, self.team.id)

    def test_option_and_recall(self):
        models.Season.objects.create(year=2026, phase=models.Season.REGULAR, is_current=True)
        called = models.Player.objects.create(
            mlb_id="424243",
            name="Called Player",
            team=self.team,
            roster_40man=True,
            roster_tripleA_option=True,
        )
        optioned = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="option_minors",
            team="mcp",
            player=self.player.mlb_id,
        )
        self.assertEqual(optioned["kind"], "option_minors", optioned)
        recalled = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="recall_option",
            player=called.mlb_id,
        )
        self.assertEqual(recalled["kind"], "recall_option", recalled)
        self.player.refresh_from_db()
        called.refresh_from_db()
        self.assertEqual(self.player.team_id, self.team.id)
        self.assertTrue(called.roster_tripleA_option)

    def test_drafts_and_auction_bids_are_refused(self):
        for code in ("rule4_draft", "rule5_draft", "auction_result", "waiver_cleared_outright"):
            result = self._call(
                self.write_token,
                filings.create_transaction_proposal,
                code=code,
                player=self.player.mlb_id,
            )
            self.assertIn("error", result, code)
            self.assertIn("cannot file", result["error"])
        self.assertFalse(models.TransactionProposal.objects.exists())

    def test_two_clubs_have_to_be_named(self):
        second = models.Team.objects.create(
            full_name="Second", short_name="Second", abbreviation="TWO"
        )
        second.owners.add(self.owner)
        result = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="release",
            player=self.player.mlb_id,
        )
        self.assertIn("TWO", result["error"])
        self.assertIn("MCP", result["error"])

    def test_a_waiver_can_be_claimed_by_the_other_club(self):
        filed = self._call(
            self.write_token,
            filings.create_transaction_proposal,
            code="waiver_request_outright",
            player=self.player.mlb_id,
        )
        self.assertEqual(filed["kind"], "waiver_request_outright", filed)
        listed = self._call(self.read_token, filings.list_open_waivers)
        self.assertEqual(len(listed["waivers"]), 1)
        self.assertEqual(listed["waivers"][0]["player"], self.player.mlb_id)

        other_user = User.objects.create_user(email="claim@example.com", password="secret")
        other_owner = models.Owner.objects.create(name="Claim", user=other_user)
        other = models.Team.objects.create(
            full_name="Claim Club", short_name="Claim", abbreviation="CLM"
        )
        other.owners.add(other_owner)
        other_token, _raw = generate_token(other_user, "claim", "read_write")
        claimed = self._call(other_token, filings.claim_waiver, listed["waivers"][0]["id"])
        self.assertEqual(claimed["team"], "CLM", claimed)
        own = self._call(self.write_token, filings.claim_waiver, listed["waivers"][0]["id"])
        self.assertIn("error", own)
        self.player.refresh_from_db()
        self.assertEqual(self.player.team_id, self.team.id)

    def test_json_api_accepts_an_abbreviation_and_refuses_a_bid(self):
        filed = self.client.post(
            "/api/v1/transactions/proposals/",
            data=json.dumps({"team": "mcp", "code": "release", "player": self.player.mlb_id}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.write_raw}",
        )
        self.assertEqual(filed.status_code, 201, filed.content)
        self.assertEqual(filed.json()["kind"], "release")

        blocked = self.client.post(
            "/api/v1/transactions/proposals/",
            data=json.dumps({"code": "auction_result", "player": self.player.mlb_id}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.write_raw}",
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("auction", blocked.json()["error"].lower())

        kinds = self.client.get(
            "/api/v1/transactions/kinds/?fileable=1",
            HTTP_AUTHORIZATION=f"Bearer {self.read_raw}",
        )
        codes = {item["code"] for item in kinds.json()["kinds"]}
        self.assertIn("non_tender", codes)
        self.assertNotIn("rule4_draft", codes)
        self.assertNotIn("auction_result", codes)

        waivers = self.client.get(
            "/api/v1/waivers/",
            HTTP_AUTHORIZATION=f"Bearer {self.read_raw}",
        )
        self.assertEqual(waivers.status_code, 200)
        self.assertEqual(waivers.json()["waivers"], [])
