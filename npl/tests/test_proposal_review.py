"""Directors approve a filing without the admin form loading every player."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from npl.admin import TransactionAssetInline
from npl.models import Owner, Player, Team, Transaction, TransactionProposal
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
        self.assertContains(page, "Post to the ledger")
        self.assertContains(page, "Needs a fix")
        self.assertNotContains(page, "Crowd 1")
        self.assertNotContains(page, "Old 1")
        self.assertFalse(any(_loads_every_player(query["sql"]) for query in captured.captured_queries))

        self.client.force_login(self.owner_user)
        owner_page = self.client.get(f"/transactions/proposals/{self.proposal.id}/")
        self.assertContains(owner_page, "Named Player")
        self.assertNotContains(owner_page, "Post to the ledger")

    def test_a_director_can_flag_and_post_from_the_page(self):
        self.client.force_login(self.director)
        url = f"/transactions/proposals/{self.proposal.id}/"
        missing = self.client.post(url, {"action": "flag", "flag_note": "   "})
        self.assertRedirects(missing, url)
        self.proposal.refresh_from_db()
        self.assertFalse(self.proposal.flagged)

        flagged = self.client.post(url, {"action": "flag", "flag_note": "Name the player."}, follow=True)
        self.assertContains(flagged, "needs a fix")
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
        self.assertNotContains(posted, "Post to the ledger")

    def test_the_admin_list_opens_the_review_page(self):
        superuser = User.objects.create_superuser(email="super@example.com", password="secret")
        self.client.force_login(superuser)
        listing = self.client.get("/admin/npl/transactionproposal/")
        self.assertContains(listing, f'href="/transactions/proposals/{self.proposal.id}/"')
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
