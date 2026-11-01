"""Every defined transaction type, checked against the 2025 and 2026 logs."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from npl.management.commands.initial_load_transactions import parse_transaction_row
from npl.models import Player, Season, Team, Transaction, TransactionProposal
from npl.transactions.audit import director_audit, load_corpus, sheet_report
from npl.transactions.catalog import KINDS

User = get_user_model()

ABSENT_FROM_THE_LOGS = {
    "il_covid",
    "il_move",
    "in_limbo",
    "death",
    "waiver_request_trade",
    "rule4_draft",
    "auction_result",
}


class SheetCorpusTests(TestCase):
    def test_logged_labels_map_and_the_cash_trade_parses(self):
        report = sheet_report()
        failed = [f"{item['name']}: {item['detail']}" for item in report["checks"] if not item["passed"]]
        self.assertEqual(failed, [])

        corpus = load_corpus()
        codes = {row["code"] for row in corpus["labels"]}
        self.assertEqual(set(KINDS) - codes, ABSENT_FROM_THE_LOGS)

        cash = next(row for row in corpus["pieces"] if row["label"] == "Cash Reserves")
        self.assertEqual(
            cash["example"]["cells"],
            ["10/13/2025", "Valkyries", "Cash Reserves", "", "", "Trade", "Speedsters", "$750,000"],
        )
        payload = parse_transaction_row(cash["example"]["cells"])
        self.assertEqual(payload["cash_considerations"], 750000)
        self.assertEqual(payload["raw_acquiring_team"], "Speedsters")
        self.assertTrue(payload["is_archive_transaction"])

        by_label = {row["label"]: row for row in corpus["labels"]}
        self.assertGreater(by_label["Trade"]["counts"]["2025"], 0)
        self.assertGreater(by_label["Trade"]["counts"]["2026"], 0)
        self.assertEqual(by_label["Option to Minors"]["code"], "option_minors")
        self.assertEqual(by_label["Option to AAA"]["code"], "option_minors")
        self.assertEqual(by_label["Option to Minors"]["counts"]["2026"], 0)
        self.assertGreater(by_label["Option to AAA"]["counts"]["2026"], 0)
        r5 = next(row for row in corpus["pieces"] if row["label"] == "R5 Draft Pick")
        self.assertEqual(r5["qualifier"], "rule5")
        self.assertEqual(r5["counts"]["2025"], 0)
        self.assertGreater(r5["counts"]["2026"], 0)


class DirectorAuditTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            email="audit-director@example.com", password="secret", is_staff=True
        )
        self.owner_user = User.objects.create_user(email="audit-owner@example.com", password="secret")
        self.client = Client()

    def test_every_defined_type_files_and_nothing_is_kept(self):
        season = Season.objects.create(year=2026, phase=Season.REGULAR, is_current=True)
        report = director_audit(self.director)
        failed = [f"{item['name']}: {item['detail']}" for item in report["checks"] if not item["passed"]]
        self.assertEqual(failed, [])
        self.assertEqual(report["audit_failed"], 0)
        self.assertEqual({row["code"] for row in report["audit_kinds"]}, set(KINDS))
        self.assertTrue(all(row["passed"] for row in report["audit_kinds"]))
        self.assertTrue(all(row["passed"] for row in report["audit_pieces"]))

        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(TransactionProposal.objects.count(), 0)
        self.assertEqual(Player.objects.filter(mlb_id__startswith="npl-audit-").count(), 0)
        self.assertFalse(Team.objects.filter(short_name__startswith="Audit").exists())
        season.refresh_from_db()
        self.assertTrue(season.is_current)
        self.assertEqual(season.phase, Season.REGULAR)
        self.assertEqual(Season.league_phase(), Season.REGULAR)

        absent = next(row for row in report["audit_kinds"] if row["code"] == "il_covid")
        self.assertIn("Not in the 2025 or 2026 transaction logs", absent["sheet_names"])
        self.assertEqual(absent["count_2025"], 0)
        self.assertEqual(absent["count_2026"], 0)
        traded = next(row for row in report["audit_kinds"] if row["code"] == "trade")
        self.assertGreater(traded["count_2026"], 0)

    def test_dashboard_is_for_directors(self):
        anonymous = self.client.get("/transactions/audit/")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/accounts/login/", anonymous.url)

        self.client.force_login(self.owner_user)
        forbidden = self.client.get("/transactions/audit/")
        self.assertEqual(forbidden.status_code, 403)
        self.assertContains(forbidden, "Directors only.", status_code=403)

        self.client.force_login(self.director)
        page = self.client.get("/transactions/audit/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["audit_failed"], 0)
        self.assertContains(page, "Transaction audit")
        self.assertContains(page, "IL: COVID")
        self.assertContains(page, "Not in the 2025 or 2026 transaction logs")
        self.assertContains(page, "Option to AAA")
        self.assertContains(page, "Option to Minors")
        self.assertContains(page, "$750,000")
        self.assertContains(page, "does not include transaction logs from earlier seasons")
        self.assertContains(page, " ET")
        self.assertNotContains(page, ">Fail<")
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(TransactionProposal.objects.count(), 0)

        home = self.client.get("/")
        self.assertContains(home, 'href="/transactions/audit/"')
