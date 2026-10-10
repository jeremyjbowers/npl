"""Transaction catalog, proposal service, and JSON API."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from npl.models import (
    DraftPick,
    DraftSession,
    Owner,
    Player,
    Team,
    Transaction,
    TransactionAsset,
    TransactionProposal,
    Waiver,
    WaiverClaim,
)
from npl.transactions.catalog import normalize_sheet_type, rl_rules, sheet_asset_qualifier
from npl.transactions.service import TransactionError, create_proposal, execute_proposal

User = get_user_model()

SHEET_ALIASES = {
    "Trade": "trade",
    "Option to AAA": "option_minors",
    "Release": "release",
    "IL: 7 Day": "il_7",
    "Recall Option": "recall_option",
    "IL: Activate": "il_activate",
    "Contract: Purchased": "purchase_contract",
    "MLB Signing": "mlb_signing",
    "Non-Tender": "non_tender",
    "Cleared: OR Waivers": "waiver_cleared_outright",
    "In Season FA": "in_season_fa",
    "IFA Signing": "ifa_signing",
    "Waiver Request: Outright": "waiver_request_outright",
    "IL: 56 Day": "il_56",
    "Minor League Signing": "minor_signing",
    "Outright Waivers": "waiver_request_outright",
    "IL: EOS": "il_eos",
    "Claimed: OR Waivers": "waiver_claimed",
    "Extension": "extension",
    "Activate": "il_activate",
    "56 Day IL": "il_56",
    "Qualifying Offer": "qualifying_offer",
    "Decline Option": "decline_option",
    "Restricted List": "restricted_place",
    "Foreign List": "foreign_place",
    "Exercise Option": "exercise_option",
    "IN Season FA": "in_season_fa",
    "Contract Amnesty": "contract_amnesty",
    "EOS IL": "il_eos",
    "RL: Activate": "restricted_activate",
    "Rule 5 Waiver Request": "waiver_request_rule5",
    "Reinstate: Foreign List": "foreign_reinstate",
    "Retirement": "retirement",
    "Minors Signing": "minor_signing",
    "Restricted List - Activate": "restricted_activate",
    "Returned: Rule 5 Waivers": "waiver_returned_rule5",
    "Option to Minors": "option_minors",
    "Contract Purchased": "purchase_contract",
    "Contract: MLB Signing": "mlb_signing",
    "Free Agent Signing": "mlb_signing",
    "Nontender": "non_tender",
    "Waivers: Cleared": "waiver_cleared_outright",
    "Waiver Claim": "waiver_claimed",
    "Waivers: Claimed": "waiver_claimed",
    "Waivers Claim": "waiver_claimed",
    "Waiver Request: Claim": "waiver_claimed",
    "Contract: Extension": "extension",
    "Contract: Exercise Option": "exercise_option",
    "Contract: Exercise Vesting Option": "exercise_vesting_option",
    "Contract: Decline Option": "decline_option",
    "Option Declined": "decline_option",
    "Contract: Qualifying Offer": "qualifying_offer",
    "release": "release",
    "Rule 5 Draft": "rule5_draft",
    "Waiver Request: Rule 5": "waiver_request_rule5",
    "Waivers: Rule 5": "waiver_request_rule5",
    "R5 Waiver Request: Cleared": "waiver_returned_rule5",
    "R5 Waiver Request: Returned": "waiver_returned_rule5",
    "IL: End of Season": "il_eos",
    "Restricted List: Place": "restricted_place",
    "Restricted List: Activate": "restricted_activate",
}


class CatalogAliasTests(TestCase):
    def test_sheet_labels_map_to_codes(self):
        for label, code in SHEET_ALIASES.items():
            self.assertEqual(normalize_sheet_type(label), code, label)

    def test_junk_ss_row_is_ignored(self):
        self.assertIsNone(normalize_sheet_type("SS"))
        self.assertIsNone(normalize_sheet_type("  "))


class ProposalServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="alpha@example.com", password="secret")
        self.other = User.objects.create_user(email="beta@example.com", password="secret")
        self.owner = Owner.objects.create(name="Alpha", user=self.user)
        self.other_owner = Owner.objects.create(name="Beta", user=self.other)
        self.team = Team.objects.create(full_name="Alpha Club", short_name="Alpha", abbreviation="ALP")
        self.other_team = Team.objects.create(full_name="Beta Club", short_name="Beta", abbreviation="BET")
        self.team.owners.add(self.owner)
        self.other_team.owners.add(self.other_owner)
        self.player = Player.objects.create(
            mlb_id="607208",
            name="Trea Turner",
            first_name="Trea",
            last_name="Turner",
            team=self.team,
        )

    def test_trade_requires_agreement(self):
        with self.assertRaises(TransactionError):
            create_proposal(
                user=self.user,
                team=self.team,
                code="trade",
                assets=[{"asset_type": "player", "player": self.player}],
            )

        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="trade",
            counterparty_team=self.other_team,
            assets=[{"asset_type": "cash", "amount": 750000, "raw_label": "Cash Reserves"}],
        )
        self.assertEqual(proposal.status, TransactionProposal.AWAITING)
        party = proposal.parties.get(role="counterparty")
        self.assertEqual(party.team_id, self.other_team.id)
        self.assertEqual(party.agreement_status, "pending")

    def test_signing_stores_contract_terms(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="mlb_signing",
            assets=[
                {
                    "asset_type": "player",
                    "raw_label": "Turner, Trea",
                    "contract_terms": {"years": 4, "total": 99588300},
                }
            ],
        )
        asset = TransactionAsset.objects.get(proposal=proposal)
        self.assertEqual(asset.contract_terms["years"], 4)
        self.assertEqual(asset.contract_terms["total"], 99588300)
        self.assertEqual(asset.raw_label, "Turner, Trea")

    def test_waiver_claim_records_priority_by_creation(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="waiver_request_outright",
            assets=[{"asset_type": "player", "player": self.player}],
            waiver_type="outright",
        )
        waiver = Waiver.objects.get(proposal=proposal)
        self.assertEqual(waiver.status, Waiver.OPEN)
        self.assertEqual(waiver.player_id, self.player.mlb_id)

        from npl.transactions.service import claim_waiver

        claim = claim_waiver(self.other, waiver)
        self.assertEqual(claim.team_id, self.other_team.id)
        self.assertEqual(list(WaiverClaim.objects.filter(waiver=waiver)), [claim])

    def test_execute_writes_ledger_without_moving_the_player(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="release",
            assets=[{"asset_type": "player", "player": self.player, "raw_label": self.player.name}],
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        execute_proposal(self.user, proposal)
        proposal.refresh_from_db()
        self.player.refresh_from_db()
        self.assertEqual(proposal.status, TransactionProposal.EXECUTED)
        self.assertEqual(Transaction.objects.filter(proposal=proposal).count(), 1)
        self.assertEqual(self.player.team_id, self.team.id)

    def test_draft_pick_sets_player_and_advances(self):
        first = DraftPick.objects.create(
            year="2027",
            season="offseason",
            draft_type="open",
            draft_round=1,
            pick_number=1,
            team=self.team,
            original_team=self.team,
        )
        second = DraftPick.objects.create(
            year="2027",
            season="offseason",
            draft_type="open",
            draft_round=1,
            pick_number=2,
            team=self.other_team,
            original_team=self.other_team,
        )
        prospect = Player.objects.create(
            mlb_id="800001",
            name="Prospect",
            first_name="Pro",
            last_name="Spect",
        )
        session = DraftSession.objects.create(
            year="2027",
            half="offseason",
            draft_type="open",
            status=DraftSession.OPEN_STATUS,
            current_pick=first,
        )
        from npl.transactions.service import submit_draft_pick

        submit_draft_pick(self.user, session, prospect)
        first.refresh_from_db()
        session.refresh_from_db()
        prospect.refresh_from_db()
        self.assertEqual(first.player_id, prospect.mlb_id)
        self.assertEqual(session.current_pick_id, second.id)
        self.assertIsNone(prospect.team_id)

    def test_limbo_restricted_list_and_rule5_picks_stay_distinct(self):
        import datetime

        self.assertEqual(sheet_asset_qualifier("R5 Draft Pick"), "rule5")
        self.assertFalse(rl_rules("PED")["accrues_salary"])
        self.assertTrue(rl_rules("Pat")["counts_against_40"])

        limbo = create_proposal(
            user=self.user,
            team=self.team,
            code="in_limbo",
            limbo_reason="pending_trade",
            assets=[{"asset_type": "player", "player": self.player}],
        )
        self.assertEqual((limbo.limbo.deadline - limbo.limbo.placed_on), datetime.timedelta(days=7))

        restricted = create_proposal(
            user=self.user,
            team=self.team,
            code="restricted_place",
            rl_type="PED",
            assets=[{"asset_type": "player", "player": self.player}],
        )
        stint = restricted.restricted_stints.get()
        self.assertEqual(stint.rl_type, "PED")
        self.assertFalse(stint.counts_against_40)

        trade = create_proposal(
            user=self.user,
            team=self.team,
            code="trade",
            counterparty_team=self.other_team,
            assets=[{"raw_label": "R5 Draft Pick"}],
        )
        self.assertEqual(trade.assets.get().qualifier, "rule5")
        self.assertEqual(trade.assets.get().asset_type, "draft_pick")


class TransactionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="api@example.com", password="secret")
        self.owner = Owner.objects.create(name="API", user=self.user)
        self.team = Team.objects.create(full_name="API Club", short_name="API", abbreviation="API")
        self.team.owners.add(self.owner)
        self.client = Client()
        self.client.force_login(self.user)

    def test_kind_list_and_proposal_create(self):
        kinds = self.client.get("/api/v1/transactions/kinds/")
        self.assertEqual(kinds.status_code, 200)
        codes = {item["code"] for item in kinds.json()["kinds"]}
        self.assertIn("trade", codes)
        self.assertIn("mlb_signing", codes)
        self.assertIn("auction_result", codes)

        created = self.client.post(
            "/api/v1/transactions/proposals/",
            data=json.dumps(
                {
                    "team": self.team.id,
                    "code": "mlb_signing",
                    "assets": [
                        {
                            "asset_type": "player",
                            "raw_label": "Glasnow, Tyler",
                            "contract_terms": {"years": 3, "total": 43374100},
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        payload = created.json()
        self.assertEqual(payload["kind"], "mlb_signing")
        self.assertEqual(payload["status"], "proposed")
        self.assertEqual(payload["assets"][0]["contract_terms"]["years"], 3)

        tools = self.client.get("/api/v1/mcp/tools/")
        self.assertEqual(tools.status_code, 200)
        names = {tool["name"] for tool in tools.json()["tools"]}
        self.assertIn("create_transaction_proposal", names)
        self.assertIn("claim_waiver", names)
        self.assertIn("submit_draft_pick", names)
        self.assertEqual(tools.json()["auth"]["type"], "bearer")


class ApiTokenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="token@example.com", password="secret")
        self.other = User.objects.create_user(email="other-token@example.com", password="secret")
        self.owner = Owner.objects.create(name="Token", user=self.user)
        self.team = Team.objects.create(full_name="Token Club", short_name="Tok", abbreviation="TOK")
        self.team.owners.add(self.owner)
        self.client = Client()

    def _proposal_body(self):
        return json.dumps({"team": self.team.id, "code": "release", "assets": []})

    def test_owner_can_mint_and_revoke_a_token(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/account/tokens/",
            {"action": "create", "name": "Trade agent", "scope": "read_write"},
        )
        self.assertEqual(created.status_code, 302)
        shown = self.client.get("/account/tokens/")
        self.assertEqual(shown.status_code, 200)
        secret = shown.context["revealed"]["secret"]
        self.assertTrue(secret.startswith("npl_"))
        self.assertContains(shown, secret)
        again = self.client.get("/account/tokens/")
        self.assertIsNone(again.context["revealed"])
        self.assertNotContains(again, secret)

        token = self.user.api_tokens.get()
        revoked = self.client.post("/account/tokens/", {"action": "revoke", "token_id": token.id})
        self.assertEqual(revoked.status_code, 302)
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)

        denied = self.client.get(
            "/api/v1/transactions/kinds/",
            HTTP_AUTHORIZATION=f"Bearer {secret}",
        )
        self.assertEqual(denied.status_code, 401)

    def test_read_token_cannot_write_and_write_token_can(self):
        from npl.api_tokens import generate_token

        read_token, read_secret = generate_token(self.user, "reader", "read")
        write_token, write_secret = generate_token(self.user, "writer", "read_write")

        anonymous = self.client.get("/api/v1/transactions/kinds/")
        self.assertEqual(anonymous.status_code, 401)

        listed = self.client.get(
            "/api/v1/transactions/kinds/",
            HTTP_AUTHORIZATION=f"Bearer {read_secret}",
        )
        self.assertEqual(listed.status_code, 200)
        read_token.refresh_from_db()
        self.assertIsNotNone(read_token.last_used_at)

        blocked = self.client.post(
            "/api/v1/transactions/proposals/",
            data=self._proposal_body(),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {read_secret}",
        )
        self.assertEqual(blocked.status_code, 403)

        created = self.client.post(
            "/api/v1/transactions/proposals/",
            data=self._proposal_body(),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {write_secret}",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["team_id"], self.team.id)

        stolen = self.client.get(
            "/api/v1/transactions/proposals/",
            HTTP_AUTHORIZATION="Bearer npl_not-a-real-token",
        )
        self.assertEqual(stolen.status_code, 401)

        other_client = Client()
        other_client.force_login(self.other)
        cannot_revoke = other_client.post(
            "/account/tokens/",
            {"action": "revoke", "token_id": write_token.id},
        )
        self.assertEqual(cannot_revoke.status_code, 404)
        write_token.refresh_from_db()
        self.assertIsNone(write_token.revoked_at)


class ProposalFlagTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="flag@example.com", password="secret")
        self.director = User.objects.create_superuser(email="director@example.com", password="secret")
        self.owner = Owner.objects.create(name="Flag", user=self.user)
        self.team = Team.objects.create(full_name="Flag Club", short_name="Flg", abbreviation="FLG")
        self.team.owners.add(self.owner)

    def test_flag_requires_a_note_and_reaches_the_club(self):
        from django.core.exceptions import ValidationError
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from npl.admin import TransactionProposalAdmin

        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="release",
            assets=[],
        )
        proposal.flagged = True
        proposal.flag_note = ""
        with self.assertRaises(ValidationError):
            proposal.full_clean()

        proposal.flag_note = "Name the player being released."
        proposal.full_clean()
        request = RequestFactory().post("/admin/npl/transactionproposal/")
        request.user = self.director

        class Changed:
            changed_data = ["flagged", "flag_note"]

        TransactionProposalAdmin(TransactionProposal, AdminSite()).save_model(
            request, proposal, Changed(), change=True
        )
        proposal.refresh_from_db()
        self.assertTrue(proposal.flagged)
        self.assertEqual(proposal.flagged_by, self.director)
        self.assertIsNotNone(proposal.flagged_at)

        self.client.force_login(self.user)
        page = self.client.get("/transactions/list/")
        self.assertContains(page, "Name the player being released.")

        detail = self.client.get(f"/api/v1/transactions/proposals/{proposal.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["flagged"])
        self.assertEqual(detail.json()["flag_note"], "Name the player being released.")
