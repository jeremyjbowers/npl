from django.test import TestCase

from npl.models import Team, Transaction
from npl.transactions.catalog import KINDS
from npl.transactions.clubs import franchise_number, tab_id_for
from npl.transactions.pending import DEPARTURE_KINDS, FORTY_MAN_DROPS
from npl.management.commands.initial_load_transactions import parse_transaction_row


class FranchiseNumberTests(TestCase):
    def test_current_and_former_names_share_a_number(self):
        self.assertEqual(franchise_number("Lion King"), 6)
        self.assertEqual(franchise_number("King"), 6)
        self.assertEqual(franchise_number("Hyperjets"), 5)
        self.assertEqual(franchise_number("Dockhounds"), 5)
        self.assertEqual(franchise_number("Absolute Sickos"), 8)
        self.assertEqual(franchise_number("Rats"), 8)
        self.assertEqual(franchise_number("Ryne"), 11)
        self.assertEqual(franchise_number("Chicago Orphans"), 11)
        self.assertEqual(franchise_number("Defenestrations"), 13)
        self.assertEqual(franchise_number("Rabbits"), 13)
        self.assertEqual(franchise_number("Nuremberg, GmbH"), 13)
        self.assertEqual(franchise_number("Qualis"), 16)
        self.assertEqual(franchise_number("Rats #8"), 8)

    def test_blank_and_non_clubs_do_not_match(self):
        self.assertIsNone(franchise_number("-"))
        self.assertIsNone(franchise_number("PHI"))
        self.assertIsNone(franchise_number("Gatherers"))

    def test_tab_id_uses_the_current_nickname(self):
        self.assertEqual(tab_id_for(13), "GmbH #13")
        self.assertEqual(tab_id_for(8), "Rats #8")


class TransactionSheetRowTests(TestCase):
    def test_trade_row_keeps_cash_and_the_other_club(self):
        payload = parse_transaction_row(
            ["10/13/2025", "Valkyries", "Cash Reserves", "-", "-", "Trade", "Speedsters", "$750,000"]
        )
        self.assertEqual(payload["raw_team"], "Valkyries")
        self.assertEqual(payload["raw_acquiring_team"], "Speedsters")
        self.assertEqual(payload["cash_considerations"], 750000)
        self.assertIsNone(payload["mlb_id"])
        self.assertTrue(payload["is_archive_transaction"])

    def test_header_and_note_rows_are_skipped(self):
        self.assertIsNone(parse_transaction_row(["Date", "Club", "Player", "SSID", "MLBID", "Transaction"]))
        self.assertIsNone(parse_transaction_row(["Seasonal Transactions"]))

    def test_dash_acquiring_club_is_empty(self):
        payload = parse_transaction_row(
            ["1/6/2025", "Defenestrations", "Dahl, David", "-", "621311", "Release", "-", ""]
        )
        self.assertEqual(payload["raw_acquiring_team"], "")
        self.assertEqual(payload["mlb_id"], "621311")

    def test_historical_name_links_the_franchise(self):
        Team.objects.create(full_name="Nuremberg GmbH", short_name="GmbH", tab_id="GmbH #13")
        transaction = Transaction(
            raw_date="3/3/2025",
            raw_team="Rabbits",
            raw_player="Draft Pick",
            raw_transaction_type="Trade",
            raw_acquiring_team="Defenestrations",
        )
        transaction.save()
        transaction.refresh_from_db()
        self.assertEqual(transaction.team.tab_id, "GmbH #13")
        self.assertEqual(transaction.acquiring_team.tab_id, "GmbH #13")


class ContractAmnestyTests(TestCase):
    def test_amnesty_drops_the_player_and_voids_the_contract(self):
        self.assertIn("voided", KINDS["contract_amnesty"]["effect"].lower())
        self.assertIn("without penalty", KINDS["contract_amnesty"]["effect"].lower())
        self.assertIn("contract_amnesty", FORTY_MAN_DROPS)
        self.assertIn("contract_amnesty", DEPARTURE_KINDS)
