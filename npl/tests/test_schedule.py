"""A 162-game season drawn as 27 weekly series."""

from datetime import date
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from npl.models import Division, League, ScheduleWeek, Season, Team, WeekGame, WeeklyPlan
from npl.schedule import ScheduleError, build_season_plan, save_season_plan


def clubs():
    made = []
    number = 1
    for league_id in (1, 2):
        for offset in range(3):
            division_id = (league_id - 1) * 3 + offset + 1
            for _ in range(4):
                made.append(
                    SimpleNamespace(
                        pk=number,
                        abbreviation=f"T{number:02d}",
                        league_id=league_id,
                        division_id=division_id,
                    )
                )
                number += 1
    return made


def signature(plan):
    return [
        tuple((series.road.abbreviation, series.home.abbreviation) for series in week.series)
        for week in plan
    ]


class ScheduleDrawTests(SimpleTestCase):
    def test_opening_week_starts_on_the_monday_of_opening_day(self):
        plan = build_season_plan(clubs(), 7, date(2026, 3, 26))
        self.assertEqual(plan[0].lineup_due, date(2026, 3, 23))
        self.assertEqual(plan[0].simulated_on, date(2026, 3, 29))
        self.assertEqual(plan[12].kind, "interleague")
        self.assertEqual(plan[19].kind, "interleague")
        self.assertEqual(len(plan), 27)
        self.assertEqual(sum(len(week.series) for week in plan), 27 * 12)

    def test_the_same_seed_draws_the_same_weeks(self):
        first = signature(build_season_plan(clubs(), 7, date(2026, 3, 26)))
        second = signature(build_season_plan(clubs(), 7, date(2026, 3, 26)))
        other = signature(build_season_plan(clubs(), 99, date(2026, 3, 26)))
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_division_rivals_meet_three_times_and_split_the_home_park(self):
        plan = build_season_plan(clubs(), 7, date(2026, 3, 26))
        by_key = {}
        for club in clubs():
            by_key[(club.league_id, club.division_id, club.pk)] = club
        homes = {}
        for week in plan:
            for series in week.series:
                homes[(series.home.pk, series.road.pk)] = homes.get((series.home.pk, series.road.pk), 0) + 1
        division = [club for club in clubs() if club.league_id == 1 and club.division_id == 1]
        for index, left in enumerate(division):
            for right in division[index + 1 :]:
                hosted = homes.get((left.pk, right.pk), 0)
                visited = homes.get((right.pk, left.pk), 0)
                self.assertEqual(sorted((hosted, visited)), [1, 2])


class ScheduleCommandTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026, is_current=True, opening_day=date(2026, 3, 26))
        leagues = [League.objects.create(name=name) for name in ("AL", "NL")]
        for league in leagues:
            divisions = [Division.objects.create(name=f"{league.name}-{index}", league=league) for index in range(3)]
            for division in divisions:
                for index in range(4):
                    Team.objects.create(
                        full_name=f"{division.name} {index}",
                        short_name=f"{division.name}{index}",
                        abbreviation=f"{league.name[0]}{division.id}{index}",
                        league=league,
                        division=division,
                    )

    def test_dry_run_saves_nothing_and_a_real_run_saves_162_games(self):
        out = StringIO()
        call_command(
            "generate_schedule",
            season=2026,
            seed=11,
            dry_run=True,
            opening_day="2026-03-26",
            stdout=out,
        )
        self.assertIn("Dry run", out.getvalue())
        self.assertEqual(ScheduleWeek.objects.count(), 0)

        call_command("generate_schedule", season=2026, seed=11, opening_day="2026-03-26", stdout=StringIO())
        self.assertEqual(ScheduleWeek.objects.filter(season=self.season).count(), 27)
        self.assertEqual(WeekGame.objects.filter(series__week__season=self.season).count(), 27 * 12 * 6)

    def test_a_played_game_blocks_regeneration(self):
        teams = list(Team.objects.filter(league__isnull=False, division__isnull=False))
        plan = build_season_plan(teams, 11, date(2026, 3, 26))
        save_season_plan(self.season, plan, 11)
        game = WeekGame.objects.filter(series__week__season=self.season).first()
        game.home_score = 3
        game.road_score = 2
        game.save()
        WeeklyPlan.objects.create(team=game.series.home_team, series=game.series)
        with self.assertRaises(CommandError):
            call_command("generate_schedule", season=2026, seed=12, stdout=StringIO())
        self.assertEqual(ScheduleWeek.objects.filter(season=self.season).count(), 27)
        self.assertEqual(WeeklyPlan.objects.count(), 1)
        with self.assertRaises(ScheduleError):
            save_season_plan(self.season, plan, 12)
