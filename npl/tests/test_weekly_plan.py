"""Owners file a weekly card. Everyone else waits until Monday night."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from npl.models import (
    Owner,
    Player,
    PlayerStatSeason,
    PlayerWeekCard,
    ScheduleWeek,
    Season,
    Team,
    WeekGame,
    WeekSeries,
    WeeklyPlan,
)
from npl.weekly_plan import script_from_plan

User = get_user_model()
POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")


class WeeklyCardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(year=2026, is_current=True)
        self.home = Team.objects.create(full_name="Home Club", short_name="Homers", abbreviation="HOM")
        self.road = Team.objects.create(full_name="Road Club", short_name="Rovers", abbreviation="ROV")
        self.owner_user = User.objects.create_user(email="home@example.com", password="secret")
        self.other_user = User.objects.create_user(email="road@example.com", password="secret")
        self.staff = User.objects.create_user(email="staff@example.com", password="secret", is_staff=True)
        home_owner = Owner.objects.create(name="Home", user=self.owner_user)
        road_owner = Owner.objects.create(name="Road", user=self.other_user)
        self.home.owners.add(home_owner)
        self.road.owners.add(road_owner)
        today = timezone.localdate()
        self.week = ScheduleWeek.objects.create(
            season=self.season,
            number=1,
            kind="league",
            lineup_due=today,
            simulated_on=today + timedelta(days=6),
        )
        self.series = WeekSeries.objects.create(week=self.week, home_team=self.home, road_team=self.road)
        WeekGame.objects.bulk_create(
            [WeekGame(series=self.series, number=number) for number in range(1, 7)]
        )
        self.hitters = []
        for index, position in enumerate(POSITIONS, start=1):
            self.hitters.append(
                Player.objects.create(
                    mlb_id=f"hit-{index}",
                    team=self.home,
                    first_name=f"Ada{index}",
                    last_name=f"Zzyzx{index}",
                    position=position,
                    bats="R",
                    roster_40man=True,
                )
            )
        self.pitchers = []
        for index in range(1, 7):
            self.pitchers.append(
                Player.objects.create(
                    mlb_id=f"pit-{index}",
                    team=self.home,
                    first_name=f"Ned{index}",
                    last_name=f"ZzyzxP{index}",
                    position="P",
                    throws="L" if index == 2 else "R",
                    roster_40man=True,
                )
            )

    def lineup_post(self):
        payload = {}
        for prefix in ("r", "l"):
            for order, (player, position) in enumerate(zip(self.hitters, POSITIONS), start=1):
                payload[f"{prefix}_player_{order}"] = player.mlb_id
                payload[f"{prefix}_pos_{order}"] = position
        return payload

    def url(self, name):
        return reverse(name, args=[self.home.short_name.lower(), 2026, 1])

    def test_owner_saves_the_card_and_the_computer_can_read_it(self):
        self.client.force_login(self.owner_user)
        lineup = self.client.post(self.url("team_lineup_week"), self.lineup_post())
        self.assertEqual(lineup.status_code, 302)
        rotation = {f"starter_{number}": pitcher.mlb_id for number, pitcher in enumerate(self.pitchers, start=1)}
        self.assertEqual(self.client.post(self.url("team_rotation_week"), rotation).status_code, 302)
        bullpen = {"usage": "traditional", "hook": "quick", "closer_1": self.pitchers[0].mlb_id, "lefty_1": self.pitchers[1].mlb_id}
        self.assertEqual(self.client.post(self.url("team_bullpen_week"), bullpen).status_code, 302)
        bench = {
            "steal": "aggressive",
            "bunt": "sacrifice",
            "hit_and_run": "normal",
            "ph_r_1": self.hitters[8].mlb_id,
            "ph_r_for_1": self.hitters[7].mlb_id,
            "ph_r_inning_1": "7",
            "ph_r_when_1": "tied_or_trailing",
            "def_out_1": self.hitters[5].mlb_id,
            "def_in_1": self.hitters[6].mlb_id,
            "def_inning_1": "8",
            "def_when_1": "leading",
            "pr_1": self.hitters[4].mlb_id,
            "pr_for_1": self.hitters[3].mlb_id,
            "pr_inning_1": "7",
            "pr_when_1": "close",
        }
        self.assertEqual(self.client.post(self.url("team_bench_week"), bench).status_code, 302)

        plan = WeeklyPlan.objects.get(team=self.home, series=self.series)
        self.assertTrue(plan.lineup_saved and plan.rotation_saved and plan.bullpen_saved and plan.bench_saved)
        script = script_from_plan(plan, 1, "L")
        self.assertEqual([player.mlb_id for player in script.lineup], [player.mlb_id for player in self.hitters])
        self.assertEqual(script.planned_starter.mlb_id, self.pitchers[0].mlb_id)
        self.assertEqual(script.closer[0].mlb_id, self.pitchers[0].mlb_id)
        self.assertEqual(script.lefty[0].mlb_id, self.pitchers[1].mlb_id)
        self.assertEqual(script.hook, "quick")
        self.assertEqual(script.bunt, "sacrifice")
        self.assertEqual(script.pinch_hit[0].for_player_id, self.hitters[7].mlb_id)
        self.assertEqual(script.defense[0].out_player_id, self.hitters[5].mlb_id)
        self.assertEqual(script.pinch_run[0].player.mlb_id, self.hitters[4].mlb_id)

    def test_the_other_club_cannot_see_or_edit_the_card_until_monday_night(self):
        self.client.force_login(self.owner_user)
        self.client.post(self.url("team_lineup_week"), self.lineup_post())

        self.client.force_login(self.other_user)
        hidden = self.client.get(self.url("team_lineup_week"))
        self.assertEqual(hidden.status_code, 200)
        self.assertNotContains(hidden, "Zzyzx")
        self.assertEqual(self.client.post(self.url("team_lineup_week"), self.lineup_post()).status_code, 403)

        self.week.lineup_due = timezone.localdate() - timedelta(days=1)
        self.week.save()
        visible = self.client.get(self.url("team_lineup_week"))
        self.assertContains(visible, "Zzyzx1")
        self.assertEqual(self.client.post(self.url("team_lineup_week"), self.lineup_post()).status_code, 403)

        self.client.force_login(self.staff)
        edited = {f"starter_{number}": self.pitchers[-1].mlb_id for number in range(1, 7)}
        self.assertEqual(self.client.post(self.url("team_rotation_week"), edited).status_code, 302)

        game = self.series.results.first()
        game.home_score = 4
        game.road_score = 2
        game.save()
        self.assertEqual(self.client.post(self.url("team_rotation_week"), edited).status_code, 403)

    def test_schedule_and_cards_pages_show_the_week(self):
        PlayerStatSeason.objects.create(
            player=self.hitters[0],
            season=2025,
            classification="1-MLB",
            hit_stats={"pa": 500, "hr": 20, "k_pct": 18.0, "bb_pct": 9.0, "babip": 0.310},
        )
        call_command("build_week_cards", season=2026, week=1, team="HOM", stdout=StringIO())
        self.assertTrue(PlayerWeekCard.objects.filter(player=self.hitters[0], week=1).exists())

        self.client.force_login(self.owner_user)
        schedule = self.client.get(reverse("schedule_year", args=[2026]))
        self.assertContains(schedule, "ROV")
        self.assertContains(schedule, "HOM")
        cards = self.client.get(self.url("team_cards_week"))
        self.assertContains(cards, "Zzyzx1")
        self.assertContains(cards, "BABIP")
        player = self.client.get(reverse("player_cards", args=[self.hitters[0].mlb_id]))
        self.assertContains(player, "week 1")
        self.assertContains(player, "No plate appearances this week")
