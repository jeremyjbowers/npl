"""The computer plays the weekly card because nobody sits the game."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from npl.computer_manager import (
    CLOSER,
    DefenseMove,
    MOPUP,
    PinchHit,
    PinchRun,
    SIRP,
    Script,
    bullpen_role,
    hook_reason,
    offensive_call,
    reliever,
)
from npl.computer_manager import ComputerManager


def arm(ident):
    return SimpleNamespace(id=ident)


def ok(_player):
    return None


class ComputerManagerTests(SimpleTestCase):
    def test_traditional_closer_pitches_a_ninth_inning_save(self):
        self.assertEqual(bullpen_role(9, 2, 0, 0, "traditional"), CLOSER)
        groups = {"closer": [arm("closer")], "sirp": [arm("setup")]}
        choice = reliever(CLOSER, groups, ok, batter_hand="R")
        self.assertEqual(choice.player.id, "closer")

    def test_mop_up_does_not_use_the_closer_when_down_four(self):
        self.assertEqual(bullpen_role(6, -4, 1, 1, "traditional"), MOPUP)
        groups = {"closer": [arm("closer")], "mopup": [arm("mop")]}
        choice = reliever(MOPUP, groups, ok)
        self.assertEqual(choice.player.id, "mop")

    def test_a_lefty_specialist_is_tried_before_setup_against_a_lefty(self):
        self.assertEqual(bullpen_role(7, 1, 0, 0, "traditional"), SIRP)
        groups = {"sirp": [arm("setup")], "lefty": [arm("lefty")]}
        choice = reliever(SIRP, groups, ok, batter_hand="L")
        self.assertEqual(choice.player.id, "lefty")

    def test_a_quick_hook_pulls_the_starter_at_four_runs(self):
        self.assertIsNotNone(hook_reason("quick", {"runs_allowed": 4, "ceiling": 100, "effort": 10}))
        self.assertIsNone(hook_reason("quick", {"runs_allowed": 3, "ceiling": 100, "effort": 10}))
        self.assertIsNotNone(hook_reason("quick", {"runs_allowed": 0, "ceiling": 100, "effort": 85}))

    def test_pinch_hit_filters_inning_score_hand_and_the_batter(self):
        rule = PinchHit(
            player=arm("ph"),
            vs_hand="L",
            for_player_id="target",
            earliest_inning=7,
            situation="tied_or_trailing",
        )
        manager = ComputerManager(Script(pinch_hit=[rule]))
        kwargs = dict(pitcher_hand="L", batter_id="target", problem=ok)
        self.assertIsNone(manager.pinch_hit(inning=6, batting_lead=-1, **kwargs).player)
        self.assertIsNone(manager.pinch_hit(inning=7, batting_lead=1, **kwargs).player)
        self.assertIsNone(manager.pinch_hit(inning=7, batting_lead=-1, pitcher_hand="R", batter_id="target", problem=ok).player)
        self.assertIsNone(manager.pinch_hit(inning=7, batting_lead=-1, pitcher_hand="L", batter_id="other", problem=ok).player)
        self.assertEqual(manager.pinch_hit(inning=7, batting_lead=-1, **kwargs).player.id, "ph")
        tired = manager.pinch_hit(inning=7, batting_lead=-1, pitcher_hand="L", batter_id="target", problem=lambda _player: "used")
        self.assertIsNone(tired.player)

    def test_defensive_replacement_and_pinch_runner_follow_the_score(self):
        manager = ComputerManager(
            Script(
                defense=[DefenseMove(out_player_id="out", player=arm("glove"), earliest_inning=8, situation="leading")],
                pinch_run=[PinchRun(player=arm("legs"), for_player_id="slow", earliest_inning=7, situation="close")],
            )
        )
        self.assertEqual(manager.defense(inning=8, fielding_lead=1, lineup_ids={"out"}, problem=ok), [("out", manager.script.defense[0].player)])
        self.assertEqual(manager.defense(inning=8, fielding_lead=0, lineup_ids={"out"}, problem=ok), [])
        self.assertEqual(manager.defense(inning=8, fielding_lead=1, lineup_ids={"out"}, problem=lambda _player: "hurt"), [])
        self.assertIsNone(manager.pinch_run(inning=7, batting_lead=2, runner_id="slow", problem=ok).player)
        self.assertEqual(manager.pinch_run(inning=7, batting_lead=0, runner_id="slow", problem=ok).player.id, "legs")

    def test_steals_scale_and_a_sacrifice_comes_before_a_hit_and_run(self):
        script = Script(steal="aggressive", bunt="sacrifice", hit_and_run="normal")
        bases = {"first": True, "second": False, "third": False}
        self.assertEqual(
            offensive_call(script, inning=7, outs=0, bases=bases, batting_lead=0, attempt_rate=0.4, draw=0.01),
            "bunt",
        )
        self.assertEqual(
            offensive_call(script, inning=7, outs=1, bases=bases, batting_lead=0, attempt_rate=0.4, draw=0.01),
            "hit_and_run",
        )
        self.assertEqual(
            offensive_call(script, inning=7, outs=1, bases=bases, batting_lead=0, attempt_rate=0.4, draw=0.5),
            "steal",
        )
        self.assertIsNone(
            offensive_call(script, inning=7, outs=1, bases=bases, batting_lead=0, attempt_rate=0.4, draw=0.7)
        )
        never = Script(steal="never", bunt="never", hit_and_run="never")
        self.assertIsNone(
            offensive_call(never, inning=7, outs=1, bases=bases, batting_lead=0, attempt_rate=0.9, draw=0.01)
        )
