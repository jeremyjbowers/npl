"""Backfill trade ids and player links, then show those moves on the player page."""

import datetime
import uuid

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from npl.models import Player, Team, Trade, Transaction, TransactionType
from npl.transactions.players import PlayerIndex
from npl.transactions.trades import persist_archive_trades


def _person(mlb_id, first, last, name=None):
    return Player.objects.create(
        mlb_id=mlb_id,
        first_name=first,
        last_name=last,
        name=name or f"{first} {last}",
    )


class NameMatchTests(SimpleTestCase):
    def index(self):
        players = [
            _stub("592450", "Aaron Judge"),
            _stub("606115", "Jose Ramirez", name="José Ramírez"),
            _stub("592518", "JD Martinez"),
            _stub("665487", "Vladimir Guerrero"),
            _stub("665489", "Vladimir Guerrero Jr."),
            _stub("100001", "Luis Garcia"),
            _stub("100002", "Luis Garcia"),
        ]
        return PlayerIndex(players)

    def test_exact_comma_form_accents_and_initials(self):
        index = self.index()
        judge = index.match("Judge, Aaron")
        self.assertEqual(judge.status, "name")
        self.assertEqual(judge.player.mlb_id, "592450")
        ramirez = index.match("Jose Ramirez")
        self.assertEqual(ramirez.status, "name")
        self.assertEqual(ramirez.player.mlb_id, "606115")
        martinez = index.match("J.D. Martinez")
        self.assertEqual(martinez.status, "name")
        self.assertEqual(martinez.player.mlb_id, "592518")

    def test_suffix_does_not_collapse_two_players(self):
        index = self.index()
        plain = index.match("Vladimir Guerrero")
        junior = index.match("Vladimir Guerrero Jr.")
        self.assertEqual(plain.player.mlb_id, "665487")
        self.assertEqual(junior.player.mlb_id, "665489")

    def test_a_close_unique_name_links_and_a_shared_name_does_not(self):
        index = self.index()
        close = index.match("Aron Judge")
        self.assertEqual(close.status, "fuzzy")
        self.assertEqual(close.player.mlb_id, "592450")
        shared = index.match("Luis Garcia")
        self.assertEqual(shared.status, "ambiguous")
        self.assertIsNone(shared.player)

    def test_mlb_id_wins_and_non_players_are_skipped(self):
        index = self.index()
        by_id = index.match("Somebody Else", "592450")
        self.assertEqual(by_id.status, "mlb_id")
        self.assertEqual(by_id.player.mlb_id, "592450")
        self.assertEqual(index.match("Draft Pick").status, "skip")
        self.assertEqual(index.match("Cash Reserves").status, "skip")
        self.assertEqual(index.match("-").status, "skip")

    def test_a_lone_last_name_links_only_when_it_is_unique(self):
        index = self.index()
        self.assertEqual(index.match("Judge").player.mlb_id, "592450")
        self.assertEqual(index.match("Garcia").status, "ambiguous")


def _stub(mlb_id, display, **kwargs):
    from types import SimpleNamespace

    first, _, last = display.partition(" ")
    payload = {
        "mlb_id": mlb_id,
        "name": kwargs.pop("name", display),
        "first_name": first,
        "last_name": last,
        "raw_name": "",
    }
    payload.update(kwargs)
    return SimpleNamespace(**payload)


class BackfillTests(TestCase):
    def setUp(self):
        self.alpha = Team.objects.create(full_name="Alpha Club", short_name="Alpha", abbreviation="ALP")
        self.beta = Team.objects.create(full_name="Beta Club", short_name="Beta", abbreviation="BET")
        self.gamma = Team.objects.create(full_name="Gamma Club", short_name="Gamma", abbreviation="GAM")
        self.judge = _person("592450", "Aaron", "Judge")
        self.other = _person("100009", "Other", "Guy")
        self.release, _ = TransactionType.objects.get_or_create(
            code="release", defaults={"transaction_type": "Release"}
        )
        self.option, _ = TransactionType.objects.get_or_create(
            code="option_minors", defaults={"transaction_type": "Option to Minors"}
        )
        self.recall, _ = TransactionType.objects.get_or_create(
            code="recall_option", defaults={"transaction_type": "Recall Option"}
        )
        self.trade_type, _ = TransactionType.objects.get_or_create(
            code="trade", defaults={"transaction_type": "Trade"}
        )
        when = datetime.date(2024, 6, 1)
        Transaction.objects.create(
            date=when,
            raw_player="Aaron Judge",
            raw_transaction_type="Trade",
            transaction_type=self.trade_type,
            team=self.alpha,
            acquiring_team=self.beta,
            raw_team="Alpha",
            raw_acquiring_team="Beta",
        )
        Transaction.objects.create(
            date=when,
            raw_player="Other Guy",
            raw_transaction_type="Trade",
            transaction_type=self.trade_type,
            team=self.beta,
            acquiring_team=self.alpha,
            raw_team="Beta",
            raw_acquiring_team="Alpha",
        )
        Transaction.objects.create(
            date=when,
            raw_player="Aaron Judge",
            raw_transaction_type="Release",
            transaction_type=self.release,
            team=self.beta,
            raw_team="Beta",
        )
        Transaction.objects.create(
            date=when,
            raw_player="Draft Pick",
            raw_transaction_type="Trade",
            transaction_type=self.trade_type,
            team=self.alpha,
            acquiring_team=self.gamma,
            raw_team="Alpha",
            raw_acquiring_team="Gamma",
        )
        Transaction.objects.create(
            date=datetime.date(2024, 7, 1),
            raw_player="Aaron Judge",
            raw_transaction_type="Option to Minors",
            transaction_type=self.option,
            team=self.alpha,
            raw_team="Alpha",
        )
        Transaction.objects.create(
            date=datetime.date(2024, 8, 1),
            raw_player="Aaron Judge",
            raw_transaction_type="Recall Option",
            transaction_type=self.recall,
            team=self.alpha,
            raw_team="Alpha",
        )
        missed = Transaction.objects.create(
            date=when,
            raw_player="Not In The Pool",
            mlb_id="592450",
            raw_transaction_type="Release",
            transaction_type=self.release,
            team=self.alpha,
            raw_team="Alpha",
        )
        Transaction.objects.filter(pk=missed.pk).update(player=None)

    def test_trade_backfill_assigns_a_uuid_and_can_be_run_again(self):
        call_command("backfill_trades", "--dry-run")
        self.assertEqual(Trade.objects.count(), 0)

        summary = persist_archive_trades()
        self.assertEqual(summary["trades"], 2)
        self.assertEqual(summary["receipts"], 3)
        trades = list(Trade.objects.all())
        self.assertTrue(all(isinstance(trade.public_id, uuid.UUID) for trade in trades))
        judge_row = Transaction.objects.get(raw_player="Aaron Judge", transaction_type=self.trade_type)
        other_row = Transaction.objects.get(raw_player="Other Guy")
        self.assertIsNotNone(judge_row.trade_id)
        self.assertEqual(judge_row.trade_id, other_row.trade_id)
        self.assertEqual(
            set(judge_row.trade.teams.values_list("short_name", flat=True)),
            {"Alpha", "Beta"},
        )
        pick = Transaction.objects.get(raw_player="Draft Pick")
        self.assertNotEqual(pick.trade_id, judge_row.trade_id)
        release = Transaction.objects.get(raw_player="Aaron Judge", transaction_type=self.release)
        self.assertIsNone(release.trade_id)

        again = persist_archive_trades()
        self.assertEqual(again["trades"], 0)
        self.assertEqual(Trade.objects.count(), 2)

    def test_player_backfill_links_names_and_ids(self):
        call_command("backfill_transaction_players", "--dry-run")
        self.assertFalse(Transaction.objects.filter(raw_player="Aaron Judge", player__isnull=False).exists())

        call_command("backfill_transaction_players")
        judge_rows = Transaction.objects.filter(raw_player="Aaron Judge")
        self.assertTrue(all(row.player_id == self.judge.mlb_id for row in judge_rows))
        self.assertTrue(all(row.mlb_id == self.judge.mlb_id for row in judge_rows))
        self.assertEqual(
            Transaction.objects.get(raw_player="Other Guy").player_id,
            self.other.mlb_id,
        )
        self.assertIsNone(Transaction.objects.get(raw_player="Draft Pick").player_id)
        missed = Transaction.objects.get(raw_player="Not In The Pool")
        self.assertEqual(missed.player_id, self.judge.mlb_id)
        self.assertEqual(missed.mlb_id, "592450")

    def test_player_page_lists_that_players_moves(self):
        call_command("backfill_trades")
        call_command("backfill_transaction_players")
        trade = Transaction.objects.get(raw_player="Aaron Judge", transaction_type=self.trade_type).trade

        page = self.client.get(f"/players/{self.judge.mlb_id}/")
        self.assertContains(page, "Transactions")
        self.assertContains(page, f"Trade {trade.public_id}")
        self.assertContains(page, "Alpha and Beta")
        self.assertContains(page, f'href="/players/{self.judge.mlb_id}/"')
        self.assertContains(page, self.release.transaction_type)
        self.assertContains(page, self.option.transaction_type)
        self.assertContains(page, self.recall.transaction_type)
        self.assertNotContains(page, "Other Guy")
        self.assertNotContains(page, "Draft Pick")

        empty = _person("100010", "Quiet", "Bench")
        quiet = self.client.get(f"/players/{empty.mlb_id}/")
        self.assertContains(quiet, "No transactions are recorded for this player.")
