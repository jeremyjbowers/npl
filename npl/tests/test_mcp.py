"""API keys, the read-only MCP JSON API, and the Streamable HTTP server."""

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from httpx import ASGITransport, AsyncClient

from npl import models
from npl.api_tokens import generate_token
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


@override_settings(ALLOWED_HOSTS=["*"])
class MCPHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="http@example.com", password="secret")
        self.owner = models.Owner.objects.create(
            name="HTTP Owner", email="http@example.com", user=self.user
        )
        _token, self.raw = generate_token(self.user, "http", "read")
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
