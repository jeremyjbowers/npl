"""Directors approve a filing without the admin form loading every player."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from npl.admin import TransactionAssetInline
from npl.models import Owner, Player, Team, Transaction, TransactionAsset, TransactionProposal
from npl.transactions.catalog import KINDS
from npl.transactions.present import VERBS, filing_headline
from npl.transactions.service import create_proposal

User = get_user_model()


def _loads_every_player(sql):
    text = " ".join(sql.split())
    return 'FROM "npl_player"' in text and " WHERE " not in text


class ProposalReviewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_user = User.objects.create_user(email="owner@example.com", password="secret")
        self.director = User.objects.create_user(
            email="director@example.com", password="secret", is_staff=True
        )
        self.owner = Owner.objects.create(name="Owner", user=self.owner_user)
        self.team = Team.objects.create(full_name="Review Club", short_name="Rev", abbreviation="REV")
        self.team.owners.add(self.owner)
        self.player = Player.objects.create(
            mlb_id="100002",
            name="Named Player",
            first_name="Named",
            last_name="Player",
            team=self.team,
        )
        self.proposal = create_proposal(
            user=self.owner_user,
            team=self.team,
            code="release",
            assets=[{"asset_type": "player", "player": self.player}],
        )
        Player.objects.bulk_create(
            [
                Player(mlb_id=f"9{i:05d}", name=f"Crowd {i}", first_name="Crowd", last_name=str(i))
                for i in range(40)
            ]
        )
        Transaction.objects.bulk_create(
            [Transaction(raw_player=f"Old {i}", team=self.team) for i in range(40)]
        )

    def test_the_review_page_reads_only_the_named_player(self):
        self.client.force_login(self.director)
        with CaptureQueriesContext(connection) as captured:
            page = self.client.get(f"/transactions/proposals/{self.proposal.id}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Named Player")
        self.assertContains(page, f"proposal {self.proposal.id}: release")
        self.assertContains(page, ">REV</a>")
        self.assertContains(page, "Approve")
        self.assertContains(page, "Return to team")
        self.assertNotContains(page, "Flagged as improper")
        self.assertNotContains(page, "<details open")
        html = page.content.decode()
        self.assertLess(html.index("Named Player"), html.index(">Impact<"))
        self.assertLess(html.index(">Impact<"), html.index(">Club<"))
        self.assertLess(html.index(">Club<"), html.index(">Director review<"))
        self.assertLess(html.index(">Approve<"), html.index('name="flag_note"'))
        self.assertNotContains(page, "Crowd 1")
        self.assertNotContains(page, "Old 1")
        self.assertFalse(any(_loads_every_player(query["sql"]) for query in captured.captured_queries))

        self.client.force_login(self.owner_user)
        owner_page = self.client.get(f"/transactions/proposals/{self.proposal.id}/")
        self.assertContains(owner_page, "Named Player")
        self.assertNotContains(owner_page, "Approve")
        self.assertNotContains(owner_page, "Return to team")
        self.assertNotContains(owner_page, "Director review")

    def test_a_director_can_flag_and_post_from_the_page(self):
        self.client.force_login(self.director)
        url = f"/transactions/proposals/{self.proposal.id}/"
        missing = self.client.post(url, {"action": "flag", "flag_note": "   "})
        self.assertRedirects(missing, f"{url}?return=1")
        self.proposal.refresh_from_db()
        self.assertFalse(self.proposal.flagged)

        flagged = self.client.post(url, {"action": "flag", "flag_note": "Name the player."}, follow=True)
        self.assertContains(flagged, "Returned to the club.")
        flagged_html = flagged.content.decode()
        self.assertLess(flagged_html.index("Flagged as improper."), flagged_html.index(">Director review<"))
        self.proposal.refresh_from_db()
        self.assertTrue(self.proposal.flagged)
        self.assertEqual(self.proposal.flag_note, "Name the player.")
        self.assertEqual(self.proposal.flagged_by, self.director)

        self.client.force_login(self.owner_user)
        refused = self.client.post(url, {"action": "post"})
        self.assertEqual(refused.status_code, 403)

        self.client.force_login(self.director)
        posted = self.client.post(url, {"action": "post"}, follow=True)
        self.assertContains(posted, "Posted to the transaction log")
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, TransactionProposal.EXECUTED)
        self.assertEqual(Transaction.objects.filter(proposal=self.proposal).count(), 1)
        self.assertContains(posted, "already on the transaction log")
        self.assertNotContains(posted, "Approve")
        self.assertNotContains(posted, "Return to team")

    def test_the_admin_list_opens_the_review_page(self):
        superuser = User.objects.create_superuser(email="super@example.com", password="secret")
        self.client.force_login(superuser)
        listing = self.client.get("/admin/npl/transactionproposal/")
        self.assertContains(
            listing,
            f'href="/transactions/proposals/{self.proposal.id}/" target="_blank" rel="noopener"',
        )
        self.assertNotContains(
            listing, f"/admin/npl/transactionproposal/{self.proposal.id}/change/"
        )

        self.client.force_login(self.director)
        opened = self.client.get(f"/admin/npl/transactionproposal/{self.proposal.id}/change/")
        self.assertRedirects(opened, f"/transactions/proposals/{self.proposal.id}/")

    def test_the_asset_form_does_not_list_every_player_or_ledger_row(self):
        request = RequestFactory().get("/admin/npl/transactionproposal/")
        request.user = User.objects.create_superuser(email="form@example.com", password="secret")
        inline = TransactionAssetInline(TransactionProposal, admin.site)
        formset = inline.get_formset(request, self.proposal)(instance=self.proposal)
        html = formset.as_p()
        player_field = html.split('for="id_assets-0-player"', 1)[1].split("</p>", 1)[0]
        ledger_field = html.split('for="id_assets-0-executed_transaction"', 1)[1].split("</p>", 1)[0]
        self.assertIn("Named Player", player_field)
        self.assertIn("vForeignKeyRawIdAdminField", player_field)
        self.assertNotIn("<select", player_field)
        self.assertNotIn("<select", ledger_field)
        self.assertNotIn("Crowd 1", html)
        self.assertNotIn("Old 1", html)

    def test_the_headline_names_the_player_the_position_and_the_club(self):
        self.player.position = "RHP"
        self.player.save(update_fields=["position"])
        self.proposal.kind = "non_tender"
        self.proposal.save(update_fields=["kind"])
        proposal = TransactionProposal.objects.prefetch_related(
            "assets__player__team", "assets__from_team", "assets__to_team"
        ).get(pk=self.proposal.pk)
        headline = filing_headline(proposal)
        self.assertEqual(
            headline["text"],
            f"proposal {proposal.id}: nontender Named Player (RHP, REV)",
        )
        self.assertFalse(headline["show_pieces"])

        other = Team.objects.create(full_name="Beta Club", short_name="Beta", abbreviation="BET")
        player_asset = proposal.assets.get()
        player_asset.to_team = other
        player_asset.save(update_fields=["to_team", "last_modified"])
        TransactionAsset.objects.create(
            proposal=proposal,
            asset_type="cash",
            amount=500000,
            from_team=other,
            to_team=self.team,
            raw_label="Cash",
        )
        proposal.kind = "trade"
        proposal.save(update_fields=["kind"])
        proposal = TransactionProposal.objects.prefetch_related(
            "assets__player__team", "assets__from_team", "assets__to_team"
        ).get(pk=proposal.pk)
        trade = filing_headline(proposal)
        self.assertEqual(
            trade["text"],
            f"proposal {proposal.id}: trade Named Player (RHP, REV) to BET and $500,000 cash from BET to REV",
        )
        self.assertTrue(trade["show_pieces"])

    def test_every_transaction_kind_has_a_review_verb(self):
        self.assertEqual(set(VERBS), set(KINDS))
