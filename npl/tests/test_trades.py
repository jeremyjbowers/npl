"""A trade is one record. Its ledger lines are the receipts under that id."""

import datetime
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from npl.models import Owner, Player, Team, Trade, Transaction
from npl.transactions.service import agree, create_proposal, execute_proposal
from npl.transactions.trades import group_log

User = get_user_model()


def _row(**kwargs):
    base = dict(
        id=1,
        trade_id=None,
        trade=None,
        date=datetime.date(2026, 6, 1),
        transaction_type=None,
        raw_transaction_type="Trade",
        team_id=None,
        team=None,
        raw_team="Alpha",
        acquiring_team_id=None,
        acquiring_team=None,
        raw_acquiring_team="Beta",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class GroupingTests(SimpleTestCase):
    def test_adjacent_pieces_between_the_same_clubs_are_one_trade(self):
        alpha_beta = [
            _row(id=1, raw_team="Alpha", raw_acquiring_team="Beta"),
            _row(id=2, raw_team="Beta", raw_acquiring_team="Alpha"),
        ]
        other = _row(id=3, raw_team="Alpha", raw_acquiring_team="Gamma")
        blocks = group_log(alpha_beta + [other])
        self.assertEqual([block["kind"] for block in blocks], ["trade", "trade"])
        self.assertEqual(blocks[0]["parties"], "Alpha and Beta")
        self.assertEqual(len(blocks[0]["rows"]), 2)
        self.assertEqual(blocks[1]["parties"], "Alpha and Gamma")

    def test_a_trade_id_keeps_pieces_together_past_another_move(self):
        trade = SimpleNamespace(id=9, date=datetime.date(2026, 6, 1), teams=SimpleNamespace(all=lambda: []))
        pieces = [
            _row(id=1, trade_id=9, trade=trade, raw_team="Alpha", raw_acquiring_team="Beta"),
            _row(id=2, raw_transaction_type="Release", raw_team="Gamma", raw_acquiring_team=""),
            _row(id=3, trade_id=9, trade=trade, raw_team="Beta", raw_acquiring_team="Alpha"),
        ]
        blocks = group_log(pieces)
        self.assertEqual(blocks[0]["kind"], "trade")
        self.assertEqual([row.id for row in blocks[0]["rows"]], [1, 3])
        self.assertEqual(blocks[0]["trade"].id, 9)
        self.assertEqual(blocks[1]["kind"], "rows")


class PostedTradeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="trade-a@example.com", password="secret")
        self.other_user = User.objects.create_user(email="trade-b@example.com", password="secret")
        self.owner = Owner.objects.create(name="Alpha", user=self.user)
        self.other_owner = Owner.objects.create(name="Beta", user=self.other_user)
        self.team = Team.objects.create(full_name="Alpha Club", short_name="Alpha", abbreviation="ALP")
        self.other = Team.objects.create(full_name="Beta Club", short_name="Beta", abbreviation="BET")
        self.team.owners.add(self.owner)
        self.other.owners.add(self.other_owner)
        self.player = Player.objects.create(
            mlb_id="910001",
            name="Deal Player",
            first_name="Deal",
            last_name="Player",
            team=self.team,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def test_posting_a_trade_creates_one_parent_over_the_receipts(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="trade",
            counterparty_team=self.other,
            assets=[
                {
                    "asset_type": "player",
                    "player": self.player,
                    "from_team": self.team,
                    "to_team": self.other,
                },
                {
                    "asset_type": "cash",
                    "amount": 500000,
                    "raw_label": "Cash",
                    "from_team": self.other,
                    "to_team": self.team,
                },
            ],
        )
        agree(self.other_user, proposal)
        execute_proposal(self.user, proposal)

        trade = Trade.objects.get()
        receipts = list(trade.receipts.order_by("id"))
        self.assertEqual(len(receipts), 2)
        self.assertEqual({row.trade_id for row in receipts}, {trade.id})
        self.assertEqual(trade.date, receipts[0].date)
        self.assertEqual(
            set(trade.teams.values_list("short_name", flat=True)),
            {"Alpha", "Beta"},
        )

        self.client.force_login(self.user)
        log = self.client.get("/transactions/")
        self.assertContains(log, f"Trade #{trade.id}")
        self.assertContains(log, "Alpha and Beta")
        self.assertContains(log, "Deal Player")
        self.assertContains(log, 'class="trade-card"')

        page = self.client.get(f"/transactions/proposals/{proposal.id}/")
        self.assertContains(page, f"Trade #{trade.id}")
        self.assertContains(page, "Alpha sends")
        self.assertContains(page, "Beta sends")

    def test_homepage_boxes_a_sheet_trade_that_has_no_id_yet(self):
        today = timezone.localdate()
        when = today - datetime.timedelta(days=today.weekday())
        Transaction.objects.create(
            date=when,
            raw_team="Alpha",
            raw_player="Player A",
            raw_transaction_type="Trade",
            raw_acquiring_team="Beta",
            team=self.team,
            acquiring_team=self.other,
        )
        Transaction.objects.create(
            date=when,
            raw_team="Beta",
            raw_player="Player B",
            raw_transaction_type="Trade",
            raw_acquiring_team="Alpha",
            team=self.other,
            acquiring_team=self.team,
        )
        home = self.client.get("/")
        self.assertContains(home, "Alpha and Beta")
        self.assertContains(home, "Player A")
        self.assertContains(home, "Player B")
        self.assertContains(home, 'class="trade-card"')
        self.assertEqual(home.content.decode().count('class="trade-card"'), 1)
