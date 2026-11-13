"""The public schedule, leaders, and club pages for the simulated season."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from npl.models import (
    Division,
    League,
    Player,
    PlayerStatSeason,
    ScheduleWeek,
    Season,
    Team,
    WeekGame,
    WeekSeries,
)
from npl.sim_season import rebuild_sim_season

User = get_user_model()


class LeaguePageTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(email="page@example.com", password="secret")
        self.client.force_login(user)
        self.season = Season.objects.create(year=2027, opening_day=date(2027, 4, 1))
        league = League.objects.create(name="National")
        division = Division.objects.create(name="East", league=league)
        self.road = Team.objects.create(
            full_name="Road Club", short_name="Rovers", abbreviation="ROV", league=league, division=division
        )
        self.home = Team.objects.create(
            full_name="Home Club", short_name="Homers", abbreviation="HOM", league=league, division=division
        )
        week = ScheduleWeek.objects.create(
            season=self.season, number=1, kind="division", lineup_due=date(2027, 4, 5), simulated_on=date(2027, 4, 11)
        )
        series = WeekSeries.objects.create(week=week, home_team=self.home, road_team=self.road)
        self.hitter = Player.objects.create(
            mlb_id="ada-1", team=self.road, first_name="Ada", last_name="Hitter", position="CF"
        )
        self.pitcher = Player.objects.create(
            mlb_id="ned-1", team=self.road, first_name="Ned", last_name="Pitcher", position="P"
        )
        WeekGame.objects.create(
            series=series,
            number=1,
            road_score=4,
            home_score=2,
            box_score={
                "away": {
                    "batting": [{
                        "player_id": self.hitter.mlb_id, "pa": 4, "ab": 4, "r": 2, "h": 2,
                        "hr": 1, "2b": 1, "3b": 0, "rbi": 2, "bb": 0, "k": 1, "hbp": 0, "sf": 0,
                    }],
                    "pitching": [{
                        "player_id": self.pitcher.mlb_id, "outs": 21, "h": 5, "r": 2,
                        "er": 2, "bb": 1, "k": 6, "hr": 0, "bf": 25,
                    }],
                },
                "home": {"batting": [], "pitching": []},
                "win_id": self.pitcher.mlb_id,
                "loss_id": None,
                "save_id": None,
            },
        )
        PlayerStatSeason.objects.create(
            player=self.hitter,
            season=2026,
            classification="1-MLB",
            is_mlb=True,
            level="MLB",
            hit_stats={"pa": 500, "plate_appearances": 500, "ab": 440, "h": 120, "hr": 18},
        )
        rebuild_sim_season(self.season)

    def test_the_schedule_opens_on_the_calendar_season_and_shows_the_series(self):
        with patch("npl.league.utils.get_current_season", return_value=2027):
            page = self.client.get(reverse("schedule"))
        self.assertContains(page, "2027 schedule")
        self.assertContains(page, "ROV 1, HOM 0")
        self.assertContains(page, "East")
        self.assertContains(page, reverse("team_schedule_year", args=["rovers", 2027]))

    def test_an_undrawn_year_says_so(self):
        page = self.client.get(reverse("schedule_year", args=[1999]))
        self.assertContains(page, "No schedule has been drawn for 1999")

    def test_leaders_rank_the_simulated_lines(self):
        page = self.client.get(reverse("leaders_year", args=[2027]))
        self.assertContains(page, "Home runs")
        self.assertContains(page, "Ada Hitter")
        self.assertContains(page, "Ned Pitcher")
        self.assertContains(page, "Wins")
        self.assertContains(page, reverse("team_stats_year", args=["rovers", 2027]))

    def test_a_club_page_lists_its_series_and_its_stat_lines(self):
        schedule = self.client.get(reverse("team_schedule_year", args=["rovers", 2027]))
        self.assertContains(schedule, "HOM")
        self.assertContains(schedule, "4–2")
        stats = self.client.get(reverse("team_stats_year", args=["homers", 2027]))
        self.assertContains(stats, "No hitting lines for 2027")
        with patch("npl.league.utils.get_current_season", return_value=2027):
            road = self.client.get(reverse("team_stats", args=["rovers"]))
        self.assertContains(road, "Ada Hitter")
        self.assertContains(road, "7.0")
        self.assertContains(road, "1–0")

    def test_the_player_page_shows_the_npl_club_beside_the_mlb_line(self):
        with patch("npl.league.utils.get_current_season", return_value=2027):
            page = self.client.get(f"/players/{self.hitter.mlb_id}/")
        self.assertContains(page, ">NPL<")
        self.assertContains(page, ">MLB<")
        self.assertContains(page, reverse("team_stats_year", args=["rovers", 2027]))
        self.assertContains(page, ">ROV<")
