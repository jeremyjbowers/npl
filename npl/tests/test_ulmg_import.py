"""ULMG season rows land on the matching NPL player."""

import os
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from npl.models import Player
from npl.ulmg_import import apply_player, import_rows, stat_lines


def _row(**overrides):
    base = {
        "player_id": 1,
        "mlbam_id": "592450",
        "fg_id": "15640",
        "current_mlb_org": "NYY",
        "bats": "R",
        "throws": "R",
        "season": 2024,
        "classification": "1-mlb",
        "level": "MLB",
        "hit_stats": None,
        "pitch_stats": None,
        "roster_status": "MLB",
        "role": "Lineup",
        "role_type": "mlb-sl",
        "mlb_org": "NYY",
        "is_mlb40man": True,
        "is_injured": False,
        "is_starter": False,
        "is_bench": False,
        "injury_description": "",
    }
    base.update(overrides)
    return base


class StatLineTests(TestCase):
    def test_hitting_line_uses_npl_keys_and_percent_scale(self):
        lines = stat_lines([
            _row(hit_stats={"pa": 675, "hr": 8, "k_pct": 0.031111111, "bb_pct": 0.05037, "wrc_plus": 104.03, "avg": 0.292}),
        ])
        line = lines["2024_majors_hit"]
        self.assertEqual(line["plate_appearances"], 675)
        self.assertEqual(line["hr"], 8)
        self.assertEqual(line["wrc_plus"], 104)
        self.assertEqual(line["k_pct"], 3.111)
        self.assertEqual(line["level"], "MLB")
        self.assertEqual(line["side"], "hit")

    def test_raw_fangraphs_keys_and_minor_league_level(self):
        lines = stat_lines([
            _row(
                season=2023,
                classification="2-milb",
                level="AAA",
                roster_status="MINORS",
                hit_stats={"PA": 214, "HR": 4, "K%": 0.261, "aLevel": "AAA"},
            ),
        ])
        line = lines["2023_minors_hit"]
        self.assertEqual(line["plate_appearances"], 214)
        self.assertEqual(line["level"], "AAA")
        self.assertEqual(line["k_pct"], 26.1)

    def test_pitching_keeps_innings_and_xera(self):
        lines = stat_lines([
            _row(hit_stats=None, pitch_stats={"g": 32, "ip": 205.1, "so": 255, "xera": 2.88, "k_9": 11.18, "era": 2.59}),
        ])
        line = lines["2024_majors_pitch"]
        self.assertEqual(line["ip"], 205.1)
        self.assertEqual(line["k"], 255)
        self.assertEqual(line["xERA"], 2.88)
        self.assertEqual(line["g"], 32)

    def test_empty_hitting_line_is_skipped(self):
        self.assertEqual(stat_lines([_row(hit_stats={"pa": 0, "hr": 0})]), {})


class ApplyTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(
            mlb_id="592450",
            name="Aaron Judge",
            first_name="Aaron",
            last_name="Judge",
            fg_id="15640",
            bats="R",
            throws="R",
            stats={"2019_majors_hit": {"year": 2019, "side": "hit", "slug": "2019_majors_hit", "plate_appearances": 1}},
        )

    def test_latest_roster_row_sets_status_and_keeps_older_stats(self):
        rows = [
            _row(
                season=2023,
                classification="2-milb",
                level="AA",
                roster_status="MINORS",
                mlb_org="NYY",
                hit_stats={"pa": 400, "hr": 20, "k_pct": 0.2},
            ),
            _row(
                season=2025,
                level="MLB",
                roster_status="IL-7",
                role="IL",
                role_type="mlb-il",
                is_injured=True,
                is_mlb40man=True,
                injury_description="oblique",
                hit_stats={"pa": 10, "hr": 2, "k_pct": 0.25},
            ),
        ]
        changed = apply_player(self.player, rows, {"15640"})
        self.assertIn("stats", changed)
        self.assertEqual(self.player.roster_status, "IL-7")
        self.assertEqual(self.player.fg_role, "MLB")
        self.assertEqual(self.player.fg_role_type, "mlb-il")
        self.assertTrue(self.player.fg_is_injured)
        self.assertTrue(self.player.fg_is_mlb40man)
        self.assertEqual(self.player.fg_injury_description, "oblique")
        self.assertEqual(self.player.mlb_org, "NYY")
        self.assertEqual(self.player.stats["2019_majors_hit"]["plate_appearances"], 1)
        self.assertEqual(self.player.stats["2023_minors_hit"]["level"], "AA")
        self.assertEqual(self.player.stats["2025_majors_hit"]["hr"], 2)
        self.assertTrue(self.player.has_appeared_in_majors)
        self.assertEqual(self.player.fg_id, "15640")
        self.assertEqual(self.player.bats, "R")

    def test_level_fills_roster_status_when_ulmg_left_it_blank(self):
        player = Player.objects.create(mlb_id="1", name="Minors Only", first_name="Minors", last_name="Only")
        apply_player(
            player,
            [_row(player_id=2, mlbam_id="1", fg_id="99", roster_status="", level="AAA", classification="2-milb", hit_stats={"pa": 50, "hr": 1})],
            set(),
        )
        self.assertEqual(player.roster_status, "MINORS")
        self.assertEqual(player.fg_role, "AAA")
        self.assertEqual(player.fg_id, "99")

    def test_list_stats_are_left_alone(self):
        self.player.stats = [{"year": 2020}]
        self.player.save(update_fields=["stats"])
        apply_player(self.player, [_row(hit_stats={"pa": 10, "hr": 1})], {"15640"})
        self.assertEqual(self.player.stats, [{"year": 2020}])

    def test_import_matches_on_mlb_id_and_can_dry_run(self):
        rows = [_row(hit_stats={"pa": 20, "hr": 3, "k_pct": 0.1})]
        summary = import_rows(rows, dry_run=True)
        self.player.refresh_from_db()
        self.assertIsNone(self.player.stats and self.player.stats.get("2024_majors_hit"))
        self.assertEqual(summary["matched"], 1)
        self.assertEqual(summary["updated"], 1)

        import_rows(rows, dry_run=False)
        self.player.refresh_from_db()
        self.assertEqual(self.player.stats["2019_majors_hit"]["plate_appearances"], 1)
        self.assertEqual(self.player.stats["2024_majors_hit"]["hr"], 3)
        self.assertEqual(self.player.roster_status, "MLB")
        self.assertEqual(self.player.fg_role, "MLB")

    def test_player_page_shows_affiliate_level_beside_roster_status(self):
        self.player.roster_status = "MINORS"
        self.player.fg_role = "AAA"
        self.player.stats = {
            "2024_minors_hit": {
                "year": 2024,
                "type": "minors",
                "level": "AAA",
                "side": "hit",
                "slug": "2024_minors_hit",
                "plate_appearances": 80,
                "hr": 6,
                "wrc_plus": 110,
            }
        }
        self.player.save()
        response = self.client.get("/players/592450/")
        self.assertContains(response, "Minors")
        self.assertContains(response, "AAA")
        self.assertContains(response, "2024")


class CommandTests(TestCase):
    def test_missing_url_refuses_to_run(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ULMG_DATABASE_URL", None)
            with self.assertRaises(CommandError):
                call_command("import_ulmg")

    def test_command_writes_matched_players(self):
        Player.objects.create(mlb_id="592450", name="Aaron Judge", first_name="Aaron", last_name="Judge")
        rows = [_row(hit_stats={"pa": 12, "hr": 4})]
        with patch.dict(os.environ, {"ULMG_DATABASE_URL": "postgres://ulmg"}):
            with patch("npl.management.commands.import_ulmg.fetch_rows", return_value=rows):
                call_command("import_ulmg")
        player = Player.objects.get(mlb_id="592450")
        self.assertEqual(player.stats["2024_majors_hit"]["hr"], 4)
        self.assertEqual(player.mlb_org, "NYY")
