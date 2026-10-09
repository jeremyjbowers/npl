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
from npl.transactions.catalog import normalize_sheet_type
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
