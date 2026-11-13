"""Weekly sims, the standings they write, and the purge that leaves MLB alone."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from npl.cards import majors_line
from npl.models import (
    Division,
    League,
    LineupSlot,
    Player,
    PlayerStatSeason,
    PlayerWeekCard,
    RotationSlot,
    ScheduleWeek,
    Season,
    SimTeamSeason,
    Team,
    TeamSeason,
    WeekGame,
    WeekSeries,
    WeeklyPlan,
)
from npl.sim_box import baseball_ip, box_from_results
from npl.sim_cards import engine_hitter_rates, engine_pitcher_rates
from npl.sim_cards import SimError
from npl.sim_season import _hit_stats, purge_sim, rebuild_sim_season
from npl.sim_week import simulate_week


POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
HITTING = {"talent": {"pa": 500, "k_pct": 20.0, "bb_pct": 8.0, "hr_pa": 0.03, "babip": 0.300}}
PITCHING = {"talent": {"ip": 150, "k_9": 9.0, "bb_9": 3.0, "hr_9": 1.1, "h_9": 8.0, "fip": 3.5}}


class RateTests(SimpleTestCase):
    def test_hitter_rates_sum_to_one(self):
        ordinary = engine_hitter_rates(HITTING["talent"])
        wild = engine_hitter_rates({"k_pct": 80, "bb_pct": 40, "hr_pa": 0.4, "babip": 0.9})
        for rates in (ordinary, wild):
            self.assertAlmostEqual(sum(rates.values()), 1.0, places=6)
            for value in rates.values():
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 1)

    def test_pitcher_rates_stay_below_one(self):
        rates = engine_pitcher_rates({"k_9": 40, "bb_9": 20, "hr_9": 8, "h_9": 20})
        for value in rates.values():
            self.assertGreaterEqual(value, 0)
            self.assertLess(value, 1)

    def test_innings_are_written_the_baseball_way(self):
        self.assertEqual(baseball_ip(20), "6.2")
        self.assertEqual(baseball_ip(3), "1.0")


class BoxTests(SimpleTestCase):
    def _pa(self, batter, pitcher, outcome, outs, runs, scored=None):
        events = []
        for runner in scored or []:
            events.append({"scored": {"runner": runner}})
        return {
            "batter_id": batter,
            "pitcher_id": pitcher,
            "outcome": outcome,
            "batter_completed": True,
            "change": {"outs_added": outs, "runs_scored": runs},
            "baserunning": events,
        }

    def test_a_five_inning_starter_keeps_the_win(self):
        results = [
            self._pa("A1", "H1", "home_run", 0, 1, scored=["A1"]),
            self._pa("A2", "H1", "ground_out", 3, 0),
            self._pa("H1B", "A-starter", "strikeout", 15, 0),
            self._pa("A2", "H1", "ground_out", 3, 0),
            self._pa("H1B", "A-save", "strikeout", 3, 0),
        ]
        box = box_from_results(results, {"A-starter": "Starter", "A-save": "Saver", "H1": "Loser"}, {}, {})
        self.assertEqual(box["score"]["away"], 1)
        self.assertEqual(box["win_id"], "A-starter")
        self.assertEqual(box["loss_id"], "H1")
        self.assertEqual(box["save_id"], "A-save")
        self.assertEqual(box["win"], "Starter")
        self.assertEqual(box["away"]["pitching"][0]["ip"], "5.0")

    def test_extra_base_hits_are_counted_on_their_own(self):
        results = [self._pa("A1", "H1", "double", 3, 0)]
        box = box_from_results(results, {}, {}, {})
        self.assertEqual(box["away"]["batting"][0]["2b"], 1)
        stats = _hit_stats({
            "pa": 1, "ab": 1, "r": 0, "h": 1, "hr": 0, "2b": 1, "3b": 0,
            "rbi": 0, "bb": 0, "k": 0, "hbp": 0, "sf": 0, "g": 1,
        })
        self.assertEqual(stats["slg"], 2)

    def test_a_short_starter_loses_the_win_to_the_reliever_who_held_the_lead(self):
        results = [
            self._pa("A1", "H1", "ground_out", 3, 0),
            self._pa("H1B", "A-starter", "strikeout", 12, 0),
            self._pa("A1", "H1", "ground_out", 3, 0),
            self._pa("H1B", "A-reliever", "strikeout", 3, 0),
            self._pa("A1", "H1", "home_run", 0, 1, scored=["A1"]),
        ]
        box = box_from_results(results, {}, {}, {})
        self.assertEqual(box["win_id"], "A-reliever")
        self.assertEqual(box["loss_id"], "H1")
        self.assertIsNone(box["save_id"])


def _player(mlb_id, team, position, first):
    return Player.objects.create(
        mlb_id=mlb_id,
        team=team,
        first_name=first,
        last_name="Sim",
        position=position,
        bats="R",
        throws="R",
    )


def _club(prefix, team, season):
    hitters = [
        _player(f"{prefix}-h{index}", team, position, f"{prefix}{index}")
        for index, position in enumerate(POSITIONS, start=1)
    ]
    pitcher = _player(f"{prefix}-p", team, "P", f"{prefix}P")
    for player in hitters:
        PlayerWeekCard.objects.create(
            player=player, season=season, week=1, true_talent={"hitting": HITTING}
        )
    PlayerWeekCard.objects.create(
        player=pitcher, season=season, week=1, true_talent={"pitching": PITCHING}
    )
    return hitters, pitcher


def _file(team, series, hitters, pitcher):
    plan = WeeklyPlan.objects.create(team=team, series=series, lineup_saved=True, rotation_saved=True)
    for hand in ("R", "L"):
        for order, (player, position) in enumerate(zip(hitters, POSITIONS), start=1):
            LineupSlot.objects.create(plan=plan, hand=hand, order=order, position=position, player=player)
    RotationSlot.objects.create(plan=plan, game_number=1, player=pitcher)
    return plan


class FakeEngine:
    def __init__(self):
        self.starts = 0

    def start(self, fixture, seed):
        self.starts += 1
        self.seed = seed
        return {
            "status": "in_progress",
            "inning": 1,
            "half": "top",
            "outs": 0,
            "bases": {},
            "score": {"away": 0, "home": 0},
            "line_score": {"away": [0], "home": []},
            "away": self._club(fixture["away"]),
            "home": self._club(fixture["home"]),
            "results": [],
        }

    def step(self, state, seed, call=None):
        away_batter = state["away"]["lineup"][0]["id"]
        home_pitcher = state["home"]["pitcher_slot"]
        away_pitcher = state["away"]["pitcher_slot"]
        home_batter = state["home"]["lineup"][0]["id"]
        state = {
            **state,
            "status": "final",
            "score": {"away": 1, "home": 0},
            "line_score": {"away": [1], "home": [0]},
            "results": [
                {
                    "batter_id": away_batter,
                    "pitcher_id": home_pitcher,
                    "outcome": "home_run",
                    "batter_completed": True,
                    "change": {"outs_added": 0, "runs_scored": 1},
                    "baserunning": [{"scored": {"runner": away_batter}}],
                },
                {
                    "batter_id": away_batter,
                    "pitcher_id": home_pitcher,
                    "outcome": "ground_out",
                    "batter_completed": True,
                    "change": {"outs_added": 3, "runs_scored": 0},
                    "baserunning": [],
                },
                {
                    "batter_id": home_batter,
                    "pitcher_id": away_pitcher,
                    "outcome": "strikeout",
                    "batter_completed": True,
                    "change": {"outs_added": 3, "runs_scored": 0},
                    "baserunning": [],
                },
            ],
        }
        return {"state": state, "result": state["results"][-1]}

    def bring_in_pitcher(self, state, pitcher, seed):
        return state

    def substitute(self, state, side, index, batter, role=None):
        return state

    def set_positions(self, state, side, changes):
        return state

    def _club(self, club):
        pitcher = club["pitchers"][0]["id"]
        return {
            "lineup": club["lineup"],
            "batter_index": 0,
            "pitcher_slot": pitcher,
            "available": [],
            "unavailable": [],
            "pending": [],
            "fatigue": {pitcher: {"effort": 0, "ceiling": 100, "runs_allowed": 0}},
        }


class RecordTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026, is_current=True)
        league = League.objects.create(name="NL")
        division = Division.objects.create(name="East", league=league)
        self.road = Team.objects.create(
            full_name="Road Club", short_name="Rovers", abbreviation="ROV", league=league, division=division
        )
        self.home = Team.objects.create(
            full_name="Home Club", short_name="Homers", abbreviation="HOM", league=league, division=division
        )
        self.week = ScheduleWeek.objects.create(
            season=self.season, number=1, kind="league", lineup_due=date(2026, 4, 6), simulated_on=date(2026, 4, 12), seed=3
        )
        self.later = ScheduleWeek.objects.create(
            season=self.season, number=2, kind="league", lineup_due=date(2026, 4, 13), simulated_on=date(2026, 4, 19), seed=4
        )
        self.hitter = _player("bat-1", self.road, "CF", "Ada")
        self.pitcher = _player("arm-1", self.road, "P", "Ned")
        self.opponent = _player("bat-2", self.home, "C", "Bea")
        TeamSeason.objects.create(team=self.road, season=self.season, cash=5, wins=99)
        PlayerStatSeason.objects.create(
            player=self.hitter,
            season=2026,
            classification="1-MLB",
            is_mlb=True,
            level="MLB",
            hit_stats={"pa": 600, "plate_appearances": 600, "ab": 520, "h": 150, "hr": 20},
        )

    def _game(self, week, road_score, home_score, box):
        series = WeekSeries.objects.create(week=week, home_team=self.home, road_team=self.road)
        return WeekGame.objects.create(
            series=series, number=1, road_score=road_score, home_score=home_score, box_score=box
        )

    def _box(self, pitching_outs):
        return {
            "away": {
                "batting": [{
                    "player_id": self.hitter.mlb_id, "pa": 4, "ab": 4, "r": 1, "h": 1,
                    "hr": 1, "rbi": 1, "bb": 0, "k": 1, "hbp": 0, "sf": 0,
                }],
                "pitching": [{
                    "player_id": self.pitcher.mlb_id, "outs": pitching_outs, "h": 0, "r": 0,
                    "er": 0, "bb": 0, "k": 1, "hr": 0, "bf": 1,
                }],
            },
            "home": {
                "batting": [{
                    "player_id": self.opponent.mlb_id, "pa": 1, "ab": 1, "r": 0, "h": 0,
                    "hr": 0, "rbi": 0, "bb": 0, "k": 1, "hbp": 0, "sf": 0,
                }],
                "pitching": [],
            },
            "win_id": self.pitcher.mlb_id,
            "loss_id": None,
            "save_id": None,
        }

    def test_rebuild_sums_outs_once_and_leaves_the_mlb_line(self):
        self._game(self.week, 1, 0, self._box(2))
        self._game(self.later, 1, 0, self._box(1))
        rebuild_sim_season(self.season)

        pitching = PlayerStatSeason.objects.get(player=self.pitcher, classification="npl")
        self.assertEqual(pitching.pitch_stats["ip"], 1.0)
        self.assertEqual(pitching.pitch_stats["w"], 2)
        self.assertEqual(pitching.pitch_stats["outs"], 3)
        hitting = PlayerStatSeason.objects.get(player=self.hitter, classification="npl")
        self.assertEqual(hitting.hit_stats["k_pct"], 25.0)
        self.assertEqual(hitting.hit_stats["hr"], 2)
        self.assertEqual(majors_line(self.hitter, 2026, "hit")["plate_appearances"], 600)
        self.assertEqual(
            sorted(line["type"] for line in self.hitter.hit_stats()),
            ["majors", "minors"],
        )

        road = SimTeamSeason.objects.get(team=self.road)
        home = SimTeamSeason.objects.get(team=self.home)
        self.assertEqual((road.wins, road.losses, road.division_place), (2, 0, 1))
        self.assertEqual((home.wins, home.losses, home.division_place), (0, 2, 2))
        self.assertEqual(TeamSeason.objects.get(team=self.road).cash, 5)
        self.assertEqual(TeamSeason.objects.get(team=self.road).wins, 99)

    def test_purge_clears_the_sim_and_keeps_the_franchise_sheet(self):
        self._game(self.week, 1, 0, self._box(3))
        rebuild_sim_season(self.season)
        result = purge_sim(self.season)
        self.assertEqual(result["games"], 1)
        self.assertFalse(PlayerStatSeason.objects.filter(classification="npl").exists())
        self.assertFalse(SimTeamSeason.objects.exists())
        self.assertTrue(PlayerStatSeason.objects.filter(classification="1-MLB").exists())
        self.assertEqual(TeamSeason.objects.get(team=self.road).cash, 5)
        self.assertIsNone(WeekGame.objects.get().road_score)
        self.assertIsNone(WeekGame.objects.get().box_score)

    def test_purging_one_week_rebuilds_from_the_games_that_remain(self):
        self._game(self.week, 3, 1, self._box(3))
        self._game(self.later, 2, 5, self._box(3))
        rebuild_sim_season(self.season)
        purge_sim(self.season, week_number=1)
        road = SimTeamSeason.objects.get(team=self.road)
        self.assertEqual((road.wins, road.losses), (0, 1))
        self.assertEqual(WeekGame.objects.get(series__week=self.week).road_score, None)
        self.assertEqual(WeekGame.objects.get(series__week=self.later).home_score, 5)
        self.assertTrue(PlayerStatSeason.objects.filter(player=self.hitter, classification="1-MLB").exists())


class WeekTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026, is_current=True)
        league = League.objects.create(name="AL")
        division = Division.objects.create(name="West", league=league)
        self.road = Team.objects.create(
            full_name="Road Club", short_name="Rovers", abbreviation="ROV", league=league, division=division
        )
        self.home = Team.objects.create(
            full_name="Home Club", short_name="Homers", abbreviation="HOM", league=league, division=division
        )
        self.week = ScheduleWeek.objects.create(
            season=self.season,
            number=1,
            kind="league",
            lineup_due=date(2026, 4, 6),
            simulated_on=date(2026, 4, 12),
            seed=11,
        )
        self.series = WeekSeries.objects.create(week=self.week, home_team=self.home, road_team=self.road)
        self.game = WeekGame.objects.create(series=self.series, number=1)
        self.road_hitters, self.road_pitcher = _club("r", self.road, self.season)
        self.home_hitters, self.home_pitcher = _club("h", self.home, self.season)
        _file(self.road, self.series, self.road_hitters, self.road_pitcher)
        _file(self.home, self.series, self.home_hitters, self.home_pitcher)
        PlayerStatSeason.objects.create(
            player=self.road_hitters[0],
            season=2026,
            classification="1-MLB",
            is_mlb=True,
            hit_stats={"pa": 400, "plate_appearances": 400, "ab": 350, "h": 100, "hr": 10},
        )
        TeamSeason.objects.create(team=self.home, season=self.season, cash=8)
        self.engine = FakeEngine()

    def test_a_filed_week_writes_the_box_and_a_second_run_skips_it(self):
        result = simulate_week(self.season, self.week, self.engine)
        self.game.refresh_from_db()
        self.assertEqual(result["played"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual((self.game.road_score, self.game.home_score), (1, 0))
        self.assertEqual(self.game.box_score["win_id"], self.road_pitcher.mlb_id)
        self.assertEqual(self.game.box_score["away"]["batting"][0]["hr"], 1)
        road = SimTeamSeason.objects.get(team=self.road)
        home = SimTeamSeason.objects.get(team=self.home)
        self.assertEqual((road.wins, road.division_place), (1, 1))
        self.assertEqual((home.losses, home.division_place), (1, 2))
        self.assertTrue(
            PlayerStatSeason.objects.filter(player=self.road_hitters[0], classification="npl", hit_stats__hr=1).exists()
        )
        self.assertEqual(majors_line(self.road_hitters[0], 2026, "hit")["plate_appearances"], 400)
        self.assertEqual(TeamSeason.objects.get(team=self.home).cash, 8)

        again = simulate_week(self.season, self.week, self.engine)
        self.assertEqual(again["skipped"], 1)
        self.assertEqual(again["played"], 0)
        self.assertEqual(self.engine.starts, 1)

    def test_a_missing_lineup_plays_nothing(self):
        WeeklyPlan.objects.filter(team=self.home).update(lineup_saved=False)
        with self.assertRaises(SimError):
            simulate_week(self.season, self.week, self.engine)
        self.game.refresh_from_db()
        self.assertIsNone(self.game.road_score)
        self.assertEqual(self.engine.starts, 0)
        self.assertFalse(SimTeamSeason.objects.exists())

    def test_purge_lets_the_week_be_played_again(self):
        simulate_week(self.season, self.week, self.engine)
        purge_sim(self.season, week_number=1)
        self.assertIsNone(WeekGame.objects.get().box_score)
        self.assertFalse(PlayerStatSeason.objects.filter(classification="npl").exists())
        simulate_week(self.season, self.week, self.engine)
        self.assertEqual(self.engine.starts, 2)
        self.assertEqual(WeekGame.objects.get().road_score, 1)
        self.assertTrue(PlayerStatSeason.objects.filter(classification="1-MLB").exists())

    @override_settings(ENGINE_URL="")
    def test_the_command_plays_the_week_named_today_and_needs_the_engine(self):
        self.week.simulated_on = timezone.localdate()
        self.week.save(update_fields=["simulated_on"])
        with self.assertRaises(CommandError) as missing:
            call_command("simulate_week", season=2026, stdout=StringIO())
        self.assertIn("ENGINE_URL", str(missing.exception))

        with self.assertRaises(CommandError):
            call_command("simulate_week", season=2026, week=9, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("simulate_week", season=1999, week=1, stdout=StringIO())

    def test_purge_command_names_what_it_cleared(self):
        simulate_week(self.season, self.week, self.engine)
        out = StringIO()
        call_command("purge_sim", season=2026, stdout=out)
        self.assertIn("npl player lines", out.getvalue())
        self.assertFalse(PlayerStatSeason.objects.filter(classification="npl").exists())
        self.assertTrue(PlayerStatSeason.objects.filter(classification="1-MLB").exists())
        self.assertEqual(TeamSeason.objects.get(team=self.home).cash, 8)
        with self.assertRaises(CommandError):
            call_command("purge_sim", season=2026, week=9, stdout=StringIO())
