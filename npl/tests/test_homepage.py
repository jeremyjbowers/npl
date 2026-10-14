"""Homepage week grouping and the deadline collector."""

import datetime
from datetime import date, timedelta
from types import SimpleNamespace

import pytz
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from npl.homepage import (
    collect_deadlines,
    group_transactions_by_week,
    select_homepage_weeks,
)
from npl.homepage import transaction_weeks
from npl.models import (
    Auction,
    Event,
    Player,
    Season,
    Team,
    Transaction,
    TransactionProposal,
    Waiver,
)


class WeekGroupingTests(SimpleTestCase):
    def test_same_week_shares_monday_newest_first_and_drops_blank_dates(self):
        monday = date(2026, 10, 5)
        wednesday = date(2026, 10, 7)
        sunday = date(2026, 10, 11)
        next_monday = date(2026, 10, 12)
        rows = [
            SimpleNamespace(date=sunday, label="sunday"),
            SimpleNamespace(date=wednesday, label="wednesday"),
            SimpleNamespace(date=None, label="blank"),
            SimpleNamespace(date=next_monday, label="next"),
            SimpleNamespace(date=monday, label="monday"),
        ]

        groups = group_transactions_by_week(rows)

        self.assertEqual([key for key, _rows in groups], [next_monday, monday])
        self.assertEqual(
            [row.label for row in groups[0][1]],
            ["next"],
        )
        self.assertEqual(
            [row.label for row in groups[1][1]],
            ["sunday", "wednesday", "monday"],
        )
        self.assertNotIn("blank", [row.label for _monday, week_rows in groups for row in week_rows])

    def test_recent_window_includes_the_previous_completed_week(self):
        today = date(2026, 10, 14)  # Wednesday; previous completed Monday is Oct 5
        previous = date(2026, 10, 5)
        current = date(2026, 10, 12)
        older = date(2026, 8, 3)
        groups = group_transactions_by_week(
            [
                SimpleNamespace(date=older),
                SimpleNamespace(date=previous + timedelta(days=2)),
                SimpleNamespace(date=current),
            ]
        )

        selected = select_homepage_weeks(groups, today)

        self.assertEqual([key for key, _rows in selected], [current, previous])

    def test_older_weeks_fill_the_page_when_nothing_is_recent(self):
        today = date(2026, 10, 12)
        first = date(2024, 1, 8)  # Monday
        second = date(2024, 1, 15)
        groups = group_transactions_by_week(
            [
                SimpleNamespace(date=first + timedelta(days=3)),
                SimpleNamespace(date=second),
                SimpleNamespace(date=None),
            ]
        )

        selected = select_homepage_weeks(groups, today)

        self.assertEqual([key for key, _rows in selected], [second, first])


class DeadlineCollectorTests(TestCase):
    def test_past_season_date_is_omitted_and_future_ifa_deadline_is_included(self):
        today = date(2026, 6, 1)
        Season.objects.create(
            year=2026,
            is_current=True,
            opening_day=date(2026, 3, 26),
            end_of_season=date(2026, 5, 1),
            ifa_deadline=date(2026, 12, 15),
            term_pay_1=None,
        )
        Event.objects.create(date=date(2020, 1, 1), title="Old meeting")
        Event.objects.create(date=today, title="Roster freeze")

        rows = collect_deadlines(today=today)
        by_label = {row["label"]: row for row in rows}

        self.assertNotIn("Opening day", by_label)
        self.assertNotIn("End of season", by_label)
        self.assertNotIn("Old meeting", by_label)
        self.assertEqual(by_label["IFA deadline"]["date"], date(2026, 12, 15))
        self.assertEqual(by_label["Roster freeze"]["date"], today)
        self.assertIn("Next transaction processing deadline", by_label)
        dates = [row["date"] for row in rows]
        self.assertEqual(dates, sorted(dates))

    def test_open_auction_and_waiver_dates_are_included(self):
        today = date(2026, 6, 1)
        now = pytz.timezone("US/Eastern").localize(datetime.datetime(2026, 6, 1, 12, 0))
        player = Player.objects.create(
            mlb_id="300001",
            name="Open Player",
            first_name="Open",
            last_name="Player",
            is_owned=False,
        )
        future = now + timedelta(days=4)
        Auction.objects.create(
            player=player,
            closes=future,
            active=True,
            is_nomination=False,
            min_bid=5,
        )
        Auction.objects.create(
            player=player,
            closes=future,
            active=True,
            is_nomination=True,
            min_bid=1,
        )
        Auction.objects.create(
            player=player,
            closes=now - timedelta(days=1),
            active=True,
            is_nomination=False,
            min_bid=1,
        )
        team = Team.objects.create(full_name="Waiver Club", short_name="Waiver")
        proposal = TransactionProposal.objects.create(kind="waiver_request_outright", originating_team=team)
        Waiver.objects.create(
            proposal=proposal,
            player=player,
            placing_team=team,
            waiver_type=Waiver.OUTRIGHT,
            status=Waiver.OPEN,
            clears_on=date(2026, 6, 8),
        )

        labels = [row["label"] for row in collect_deadlines(today=today, now=now)]

        self.assertEqual(labels.count("Open Player"), 1)
        self.assertIn("Open Player Outright waiver", labels)

    def test_logged_transactions_group_on_the_homepage_and_unowned_players_cap_at_40(self):
        today = timezone.localdate()
        this_monday = today - timedelta(days=today.weekday())
        previous_monday = this_monday - timedelta(days=7)
        Transaction.objects.create(date=previous_monday, raw_player="Monday Player", raw_team="Alpha")
        Transaction.objects.create(
            date=previous_monday + timedelta(days=6),
            raw_player="Sunday Player",
            raw_acquiring_team="Beta",
        )
        Transaction.objects.create(raw_player="No Date")
        Transaction.objects.create(date=previous_monday - timedelta(days=400), raw_player="Ancient Player")
        for i in range(41):
            Player.objects.create(
                mlb_id=str(400000 + i),
                name=f"Free Agent {i:02d}",
                first_name="Free",
                last_name=f"Agent{i:02d}",
                is_owned=False,
                position="SS",
                mlb_org="NYY",
                roster_status="MLB",
            )

        weeks = transaction_weeks(today=today)
        self.assertEqual([week["monday"] for week in weeks], [previous_monday])
        self.assertEqual(
            [row.calculated_player for row in weeks[0]["transactions"]],
            ["Sunday Player", "Monday Player"],
        )
        self.assertEqual(weeks[0]["transactions"][0].calculated_acquiring_team, "Beta")

        response = self.client.get("/")
        self.assertContains(response, "Monday Player")
        self.assertContains(response, "Sunday Player")
        self.assertNotContains(response, "No Date")
        self.assertNotContains(response, "Ancient Player")
        self.assertContains(response, "Free Agent00")
        self.assertNotContains(response, "Free Agent40")
        self.assertContains(response, "Showing 40.")
        self.assertContains(response, "Majors")
        self.assertContains(response, "NYY")

    def test_homepage_renders_the_weekly_board(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/transactions/trades/"')
        self.assertContains(response, 'href="/transactions/other/"')
        self.assertContains(response, "There is no open auction.")
        self.assertContains(response, "Players page")
        self.assertNotContains(response, "85-man")
        self.assertNotContains(response, 'target="_blank"')
