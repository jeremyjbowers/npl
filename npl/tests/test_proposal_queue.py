"""Directors see one Monday's filings, and can step to another week or the closed ones."""

import datetime

import pytz
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from npl.models import Owner, Player, Team, TransactionProposal
from npl.transactions.service import create_proposal, next_processing_week
from npl.transactions.weeks import processing_monday, review_monday

User = get_user_model()
EASTERN = pytz.timezone("US/Eastern")


def at(year, month, day, hour, minute=0):
    return EASTERN.localize(datetime.datetime(year, month, day, hour, minute))


class ProcessingWeekTests(TestCase):
    def test_monday_afternoon_misses_that_weeks_cutoff(self):
        monday_morning = at(2026, 11, 23, 10)
        monday_cutoff = at(2026, 11, 23, 13)
        monday_late = at(2026, 11, 23, 13, 5)
        sunday_night = at(2026, 11, 22, 23)
        tuesday = at(2026, 11, 24, 9)

        self.assertEqual(processing_monday(monday_morning), datetime.date(2026, 11, 23))
        self.assertEqual(review_monday(monday_morning), datetime.date(2026, 11, 23))
        self.assertEqual(processing_monday(monday_cutoff), datetime.date(2026, 11, 30))
        self.assertEqual(review_monday(monday_cutoff), datetime.date(2026, 11, 23))
        self.assertEqual(processing_monday(monday_late), datetime.date(2026, 11, 30))
        self.assertEqual(review_monday(monday_late), datetime.date(2026, 11, 23))
        self.assertEqual(processing_monday(sunday_night), datetime.date(2026, 11, 23))
        self.assertEqual(review_monday(sunday_night), datetime.date(2026, 11, 23))
        self.assertEqual(processing_monday(tuesday), datetime.date(2026, 11, 30))
        self.assertEqual(review_monday(tuesday), datetime.date(2026, 11, 30))
        self.assertEqual(next_processing_week(monday_late), datetime.date(2026, 11, 30))

    def test_a_late_filing_is_stored_on_the_next_monday(self):
        user = User.objects.create_user(email="late@example.com", password="secret")
        owner = Owner.objects.create(name="Late", user=user)
        team = Team.objects.create(full_name="Late Club", short_name="Late", abbreviation="LATE")
        team.owners.add(owner)
        player = Player.objects.create(
            mlb_id="500001", name="Late Player", first_name="Late", last_name="Player", team=team
        )
        late = at(2026, 11, 23, 13, 5)
        with timezone.override(EASTERN):
            from unittest.mock import patch

            with patch("npl.transactions.weeks.timezone.now", return_value=late):
                proposal = create_proposal(
                    user=user,
                    team=team,
                    code="release",
                    assets=[{"asset_type": "player", "player": player}],
                )
        self.assertEqual(proposal.processing_week, datetime.date(2026, 11, 30))


class ProposalQueueTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_user = User.objects.create_user(email="owner@example.com", password="secret")
        self.director = User.objects.create_user(
            email="director@example.com", password="secret", is_staff=True
        )
        self.owner = Owner.objects.create(name="Owner", user=self.owner_user)
        self.team = Team.objects.create(full_name="Queue Club", short_name="Queue", abbreviation="QUE")
        self.team.owners.add(self.owner)
        self.this_week = self._filing("500011", "Ada", "This", datetime.date(2026, 11, 23))
        self.next_week = self._filing("500012", "Bea", "Next", datetime.date(2026, 11, 30))
        self.closed = self._filing("500013", "Cal", "Closed", datetime.date(2026, 11, 23), executed=True)
        self.previous = self._filing("500014", "Dee", "Past", datetime.date(2026, 11, 16))
        self.moment = at(2026, 11, 23, 14)

    def _filing(self, mlb_id, first, last, week, executed=False):
        player = Player.objects.create(
            mlb_id=mlb_id,
            name=f"{first} {last}",
            first_name=first,
            last_name=last,
            team=self.team,
        )
        proposal = create_proposal(
            user=self.owner_user,
            team=self.team,
            code="release",
            assets=[{"asset_type": "player", "player": player}],
        )
        proposal.processing_week = week
        if executed:
            proposal.status = TransactionProposal.EXECUTED
        proposal.save(update_fields=["processing_week", "status", "last_modified"])
        return proposal

    def _page(self, query=""):
        from unittest.mock import patch

        self.client.force_login(self.director)
        with patch("npl.transactions.weeks.timezone.now", return_value=self.moment):
            return self.client.get(f"/transactions/proposals/{query}")

    def test_the_default_page_is_this_weeks_open_filings(self):
        page = self._page()
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page,
            f'href="/transactions/proposals/{self.this_week.id}/" target="_blank" rel="noopener"',
        )
        self.assertContains(page, "Ada This")
        self.assertNotContains(page, "Bea Next")
        self.assertNotContains(page, "Cal Closed")
        self.assertNotContains(page, "Dee Past")
        self.assertContains(page, "Nov 30")
        self.assertContains(page, "1:00 PM ET")
        self.assertContains(page, "this week")

    def test_a_director_can_look_ahead_and_back_and_at_closed_filings(self):
        ahead = self._page("?week=2026-11-30")
        self.assertEqual(ahead.context["selected_week"], datetime.date(2026, 11, 30))
        self.assertContains(ahead, "Bea Next")
        self.assertNotContains(ahead, "Ada This")

        back = self._page("?week=2026-11-16")
        self.assertContains(back, "Dee Past")
        self.assertNotContains(back, "Ada This")

        closed = self._page("?week=2026-11-23&state=closed")
        self.assertContains(closed, "Cal Closed")
        self.assertNotContains(closed, "Ada This")

        everything = self._page("?week=2026-11-23&state=all")
        self.assertContains(everything, "Ada This")
        self.assertContains(everything, "Cal Closed")
        self.assertNotContains(everything, "Bea Next")

    def test_an_owner_cannot_open_the_list(self):
        self.client.force_login(self.owner_user)
        refused = self.client.get("/transactions/proposals/")
        self.assertEqual(refused.status_code, 403)
        self.assertContains(refused, "Directors only.", status_code=403)
