"""Weekly cards: last year's true talent, then the usage that updates it."""

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from io import StringIO

from npl.cards import (
    blend_hitter,
    build_card,
    hitter_counts,
    hitter_rates,
    hitter_true_talent,
    pitcher_true_talent,
    prior_weight,
    regress_hitter,
)
from npl.models import Player, PlayerStatSeason, PlayerWeekCard, Season, Team
from npl.week_cards import refresh_cards


PRIOR = {"plate_appearances": 600, "hr": 18, "k_pct": 30.0, "bb_pct": 8.0, "babip": 0.300}
WILD = {"plate_appearances": 80, "hr": 8, "k_pct": 40.0, "bb_pct": 2.0, "babip": 0.450}


class CardMathTests(SimpleTestCase):
    def test_week_one_ignores_a_wild_live_line(self):
        card = build_card(PRIOR, WILD, None, None, None, None, 1)
        prior = hitter_true_talent(PRIOR)
        self.assertEqual(card["hitting"]["talent"]["babip"], prior["babip"])
        self.assertEqual(card["hitting"]["week"]["pa"], 0.0)
        self.assertTrue(card["hitting"]["usage_known"])
        self.assertEqual(card["prior_weight"], 1.0)

    def test_a_later_week_sits_between_the_prior_and_the_live_line(self):
        self.assertEqual(prior_weight(14), 0.5)
        self.assertEqual(prior_weight(27), 0.15)
        prior = hitter_true_talent(PRIOR)
        live = {"plate_appearances": 400, "hr": 30, "k_pct": 30.0, "bb_pct": 8.0, "babip": 0.360}
        card = build_card(PRIOR, live, hitter_counts(live), None, None, None, 4)
        babip = card["hitting"]["talent"]["babip"]
        self.assertGreater(babip, prior["babip"])
        self.assertLess(babip, 0.360)

    def test_regression_leaves_strikeout_rate_alone(self):
        counts = hitter_counts(PRIOR)
        regressed = regress_hitter(counts)
        self.assertEqual(hitter_rates(regressed)["k_pct"], 30.0)
        raw_rate = counts["hr"] / counts["pa"]
        regressed_rate = regressed["hr"] / regressed["pa"]
        self.assertGreater(regressed_rate, raw_rate)
        self.assertLess(regressed_rate, 0.031)

    def test_pitcher_regression_keeps_his_own_strikeouts(self):
        talent = pitcher_true_talent({"ip": 100, "k": 100, "bb": 30, "hr": 20, "h": 110})
        self.assertEqual(talent["k_9"], 9.0)
        self.assertLess(talent["hr_9"], 1.8)

    def test_week_usage_is_the_delta_and_unknown_without_a_previous_card(self):
        previous = hitter_counts({"plate_appearances": 100, "hr": 2, "k_pct": 20, "bb_pct": 8, "babip": 0.300})
        live = {"plate_appearances": 140, "hr": 5, "k_pct": 20, "bb_pct": 8, "babip": 0.300}
        known = build_card(PRIOR, live, previous, None, None, None, 2)
        self.assertEqual(known["hitting"]["week"]["pa"], 40.0)
        self.assertTrue(known["hitting"]["usage_known"])
        self.assertIsNotNone(known["hitting"]["talent"])

        unknown = build_card(PRIOR, live, None, None, None, None, 2)
        self.assertFalse(unknown["hitting"]["usage_known"])
        self.assertEqual(unknown["hitting"]["week"]["pa"], 0.0)
        self.assertIsNotNone(unknown["hitting"]["talent"])

    def test_week_four_blend_uses_the_shrinking_prior(self):
        prior = regress_hitter(hitter_counts(PRIOR))
        season = hitter_counts(WILD)
        blended = blend_hitter(prior, season, 4)
        self.assertIsNotNone(blended)


class WeekCardCommandTests(TestCase):
    def test_refresh_folds_the_new_plate_appearances_into_the_next_card(self):
        season = Season.objects.create(year=2026, is_current=True)
        team = Team.objects.create(full_name="Card Club", short_name="Cards", abbreviation="CRD")
        player = Player.objects.create(
            mlb_id="card-1",
            team=team,
            first_name="Ada",
            last_name="Zzyzx",
            position="CF",
            roster_40man=True,
        )
        PlayerStatSeason.objects.create(
            player=player,
            season=2025,
            classification="1-MLB",
            hit_stats={"pa": 600, "hr": 18, "k_pct": 22.0, "bb_pct": 8.0, "babip": 0.290},
        )
        live = PlayerStatSeason.objects.create(
            player=player,
            season=2026,
            classification="1-MLB",
            hit_stats={"pa": 40, "hr": 1, "k_pct": 20.0, "bb_pct": 10.0, "babip": 0.320},
        )
        refresh_cards(season, 1, [player])
        first = PlayerWeekCard.objects.get(player=player, week=1)
        self.assertEqual(first.prior_weight, 1.0)
        self.assertEqual(first.week_usage["hitting"]["pa"], 0.0)

        live.hit_stats = {"pa": 70, "hr": 3, "k_pct": 20.0, "bb_pct": 10.0, "babip": 0.320}
        live.save()
        fresh = Player.objects.prefetch_related("stat_seasons").get(pk=player.pk)
        refresh_cards(season, 2, [fresh])
        second = PlayerWeekCard.objects.get(player=player, week=2)
        self.assertEqual(second.week_usage["hitting"]["pa"], 30.0)
        self.assertTrue(second.week_usage["hitting_known"])
        self.assertLess(second.prior_weight, 1.0)

        out = StringIO()
        call_command("build_week_cards", season=2026, week=3, team="CRD", stdout=out)
        self.assertIn("Wrote 1", out.getvalue())
        self.assertTrue(PlayerWeekCard.objects.filter(player=player, week=3).exists())
