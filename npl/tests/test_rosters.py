import unittest
from types import SimpleNamespace

from npl.rosters import build_sections, is_active_mlb, order_players, position_bucket, summarize


def player(**kwargs):
    base = dict(
        roster_40man=False,
        roster_30man=False,
        roster_tripleA=False,
        roster_tripleA_option=False,
        roster_7dayIL=False,
        roster_56dayIL=False,
        roster_eosIL=False,
        roster_restricted=False,
        roster_outrighted=False,
        roster_foreign=False,
        roster_retired=False,
        roster_nonroster=False,
        roster_doubleA=False,
        roster_singleA=False,
        simple_position="C",
        mls_time="",
        mls_year="",
        last_name="A",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class RosterTests(unittest.TestCase):
    def test_position_buckets(self):
        self.assertEqual(position_bucket("SS"), "IF")
        self.assertEqual(position_bucket("CF"), "OF")
        self.assertEqual(position_bucket("LHP"), "P")
        self.assertEqual(position_bucket("DH"), "UT")
        self.assertEqual(position_bucket(None), "UT")

    def test_optioned_40_man_is_not_active_mlb(self):
        self.assertTrue(is_active_mlb(player(roster_40man=True, simple_position="P")))
        self.assertFalse(
            is_active_mlb(player(roster_40man=True, roster_tripleA_option=True))
        )

    def test_sections_are_one_pass_and_skip_empty_lists(self):
        active = player(roster_40man=True, simple_position="SS", last_name="Baker")
        optioned = player(
            roster_40man=True,
            roster_tripleA_option=True,
            simple_position="P",
            last_name="Adams",
        )
        catcher = player(roster_tripleA=True, simple_position="C", last_name="Young")

        sections = build_sections([catcher, optioned, active])
        titles = [section["title"] for section in sections]

        self.assertEqual(titles, ["MLB Roster", "AAA Roster", "AAA Roster (On Option)"])
        self.assertEqual(sections[0]["players"], [active])
        self.assertEqual(sections[1]["players"], [catcher])
        self.assertEqual(sections[2]["players"], [optioned])

    def test_pitchers_lead_each_section(self):
        ordered = order_players(
            [
                player(simple_position="C", last_name="Young"),
                player(simple_position="P", last_name="Adams", mls_time="1.000"),
                player(simple_position="P", last_name="Baker", mls_time="3.000"),
            ]
        )
        self.assertEqual([p.simple_position for p in ordered[:2]], ["P", "P"])
        self.assertEqual(ordered[-1].last_name, "Young")
        self.assertEqual(
            [p.last_name for p in ordered if p.simple_position == "P"],
            ["Baker", "Adams"],
        )

    def test_summary_counts_positions_once(self):
        summary = summarize(
            [
                player(simple_position="C", roster_40man=True),
                player(simple_position="SS"),
                player(simple_position="RF"),
                player(simple_position="P", roster_40man=True),
            ]
        )
        self.assertEqual(summary["total_count"], 4)
        self.assertEqual(summary["roster_40_man_count"], 2)
        self.assertEqual(summary["pos_counts"]["C"], 1)
        self.assertEqual(summary["pos_counts"]["IF"], 1)
        self.assertEqual(summary["pos_counts"]["OF"], 1)
        self.assertEqual(summary["pos_counts"]["P"], 1)
