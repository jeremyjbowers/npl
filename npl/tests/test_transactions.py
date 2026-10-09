import json

from django.test import Client, TestCase

from npl.models import (
    DraftPick,
    DraftSession,
    Owner,
    Player,
    Team,
    TransactionProposal,
    Waiver,
    WaiverClaim,
)
from npl.transactions.catalog import normalize_sheet_type
from npl.transactions.service import (
    TransactionError,
    agree,
    claim_waiver,
    create_proposal,
)
from users.models import User


ALIASES = {
    "Trade": "trade",
    "Option to AAA": "option_minors",
    "Option to Minors": "option_minors",
    "Release": "release",
    "release": "release",
    "IL: 7 Day": "il_7",
    "Recall Option": "recall_option",
    "IL: Activate": "il_activate",
    "Contract: Purchased": "purchase_contract",
    "Contract Purchased": "purchase_contract",
    "MLB Signing": "mlb_signing",
    "Contract: MLB Signing": "mlb_signing",
    "Free Agent Signing": "mlb_signing",
    "Non-Tender": "non_tender",
    "Nontender": "non_tender",
    "Cleared: OR Waivers": "waiver_cleared_outright",
    "Waivers: Cleared": "waiver_cleared_outright",
    "In Season FA": "in_season_fa",
    "IN Season FA": "in_season_fa",
    "IFA Signing": "ifa_signing",
    "Waiver Request: Outright": "waiver_request_outright",
    "Outright Waivers": "waiver_request_outright",
    "IL: 56 Day": "il_56",
    "56 Day IL": "il_56",
    "Minor League Signing": "minor_signing",
    "Minors Signing": "minor_signing",
    "IL: EOS": "il_eos",
    "EOS IL": "il_eos",
    "IL: End of Season": "il_eos",
    "Claimed: OR Waivers": "waiver_claimed",
    "Waiver Claim": "waiver_claimed",
    "Waivers: Claimed": "waiver_claimed",
    "Waivers Claim": "waiver_claimed",
    "Waiver Request: Claim": "waiver_claimed",
    "Extension": "extension",
    "Contract: Extension": "extension",
    "Qualifying Offer": "qualifying_offer",
    "Contract: Qualifying Offer": "qualifying_offer",
    "Decline Option": "decline_option",
    "Contract: Decline Option": "decline_option",
    "Option Declined": "decline_option",
    "Restricted List": "restricted_place",
    "Restricted List: Place": "restricted_place",
    "Foreign List": "foreign_place",
    "Exercise Option": "exercise_option",
    "Contract: Exercise Option": "exercise_option",
    "Contract: Exercise Vesting Option": "exercise_vesting_option",
    "Contract Amnesty": "contract_amnesty",
    "RL: Activate": "restricted_activate",
    "Restricted List - Activate": "restricted_activate",
    "Restricted List: Activate": "restricted_activate",
    "Rule 5 Waiver Request": "waiver_request_rule5",
    "Waiver Request: Rule 5": "waiver_request_rule5",
    "Waivers: Rule 5": "waiver_request_rule5",
    "Reinstate: Foreign List": "foreign_reinstate",
    "Retirement": "retirement",
    "Returned: Rule 5 Waivers": "waiver_returned_rule5",
    "R5 Waiver Request: Cleared/Returned": "waiver_returned_rule5",
    "Rule 5 Draft": "rule5_draft",
    "SS": None,
}


class AliasTests(TestCase):
    def test_sheet_labels_collapse_to_codes(self):
        for label, code in ALIASES.items():
            self.assertEqual(normalize_sheet_type(label), code, label)


class ProposalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@example.com", password="secret")
        self.other = User.objects.create_user(email="b@example.com", password="secret")
        self.owner = Owner.objects.create(name="A", user=self.user)
        self.other_owner = Owner.objects.create(name="B", user=self.other)
        self.team = Team.objects.create(full_name="Cheesequake Cheddar", short_name="Cheddar")
        self.counter = Team.objects.create(full_name="Asbury Park Bosses", short_name="Bosses")
        self.team.owners.add(self.owner)
        self.counter.owners.add(self.other_owner)
        self.player = Player.objects.create(mlb_id="608369", name="Seager, Corey", team=self.team)
        self.free_agent = Player.objects.create(mlb_id="665489", name="Guerrero Jr., Vladimir")

    def test_trade_waits_for_the_other_club(self):
        with self.assertRaises(TransactionError):
            create_proposal(user=self.user, team=self.team, code="trade", assets=[])
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="trade",
            counterparty_team=self.counter,
            assets=[
                {
                    "asset_type": "player",
                    "player": self.player,
                    "from_team": self.team,
                    "to_team": self.counter,
                },
                {"asset_type": "cash", "amount": 750000, "raw_label": "Cash Reserves"},
            ],
        )
        self.assertEqual(proposal.status, TransactionProposal.AWAITING)
        proposal = agree(self.other, proposal)
        self.assertEqual(proposal.status, TransactionProposal.AGREED)

    def test_signing_stores_contract_terms(self):
        terms = {"years": 4, "total": 99588300, "points": "173"}
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="mlb_signing",
            contract_terms=terms,
            assets=[
                {
                    "asset_type": "player",
                    "player": self.free_agent,
                    "raw_label": self.free_agent.name,
                    "amount": 99588300,
                    "contract_terms": terms,
                }
            ],
        )
        asset = proposal.assets.get()
        self.assertEqual(asset.contract_terms["years"], 4)
        self.assertEqual(asset.amount, 99588300)
        self.assertEqual(proposal.status, TransactionProposal.PROPOSED)

    def test_waiver_claim(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="waiver_request_outright",
            assets=[{"asset_type": "player", "player": self.player}],
            waiver_type="outright",
            veteran_disposition="keep_40",
        )
        waiver = Waiver.objects.get(proposal=proposal)
        self.assertEqual(waiver.status, Waiver.OPEN)
        self.assertEqual(waiver.veteran_disposition, "keep_40")
        claim = claim_waiver(self.other, waiver)
        self.assertEqual(claim.team, self.counter)
        self.assertEqual(WaiverClaim.objects.filter(waiver=waiver).count(), 1)

    def test_api_kinds_and_create(self):
        client = Client()
        kinds = client.get("/api/v1/transactions/kinds/")
        self.assertEqual(kinds.status_code, 200)
        codes = {item["code"] for item in kinds.json()["kinds"]}
        self.assertIn("trade", codes)
        self.assertIn("rule4_draft", codes)

        client.force_login(self.user)
        created = client.post(
            "/api/v1/transactions/proposals/",
            data=json.dumps(
                {
                    "team": self.team.id,
                    "code": "in_season_fa",
                    "contract_terms": {"years": 1, "total": 760000},
                    "assets": [
                        {
                            "asset_type": "player",
                            "player": self.free_agent.mlb_id,
                            "amount": 760000,
                            "contract_terms": {"years": 1, "total": 760000},
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(body["kind"], "in_season_fa")
        self.assertEqual(body["assets"][0]["amount"], 760000)

    def test_draft_pick_records_a_proposal(self):
        pick = DraftPick.objects.create(
            year="2027",
            season="offseason",
            draft_type="open",
            draft_round=1,
            pick_number=1,
            team=self.team,
        )
        session = DraftSession.objects.create(
            year="2027",
            half="offseason",
            draft_type="rule4",
            status="open",
            current_pick=pick,
        )
        from npl.transactions.service import submit_draft_pick

        proposal = submit_draft_pick(self.user, session, self.free_agent.mlb_id)
        self.assertEqual(proposal.kind, "rule4_draft")
        pick.refresh_from_db()
        self.assertIsNone(pick.player_id)
        session.refresh_from_db()
        self.assertEqual(session.status, DraftSession.COMPLETE)
