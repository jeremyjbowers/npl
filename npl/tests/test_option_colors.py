"""Roster colors for option years and buyouts."""

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.contrib.auth.models import AnonymousUser

from npl.sheetload import (
    ARBITRATION,
    BUYOUT_CELL_CLASS,
    CLUB_OPTION,
    GUARANTEED,
    PLAYER_OPTION,
    PRE_ARB_0,
    PRE_ARB_1,
    PRE_ARB_2,
    VESTING_OPTION,
    buyout_cell_class,
    contract_has_buyout,
    salary_cell_class,
)


def year(amount, salary_class, salary_label):
    return SimpleNamespace(amount=amount, salary_class=salary_class, salary_label=salary_label)


def contract(years, buyout_amount=None):
    return SimpleNamespace(years=years, buyout_amount=buyout_amount)


def player(contract=None, **kwargs):
    base = dict(
        player_level="",
        pending_hint=None,
        is_owned=True,
        name="Ada Player",
        mlb_id="1",
        position="P",
        get_roster_status="Active",
        age=28,
        mlb_org="NYY",
        roster_40man=True,
        mls_time="3.000",
        mls_year="",
        options=1,
        status="active",
        simple_position="P",
        contract=contract,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class OptionColorTests(SimpleTestCase):
    def test_option_years_map_to_distinct_markers(self):
        markers = {
            CLUB_OPTION: salary_cell_class(CLUB_OPTION),
            VESTING_OPTION: salary_cell_class(VESTING_OPTION),
            PLAYER_OPTION: salary_cell_class(PLAYER_OPTION),
        }
        self.assertEqual(
            markers,
            {
                CLUB_OPTION: "salary-club_option",
                VESTING_OPTION: "salary-vesting_option",
                PLAYER_OPTION: "salary-player_option",
            },
        )
        self.assertEqual(len(set(markers.values())), 3)

    def test_guaranteed_pre_arb_and_arbitration_stay_plain(self):
        for name in (GUARANTEED, PRE_ARB_0, PRE_ARB_1, PRE_ARB_2, ARBITRATION, "", None):
            self.assertEqual(salary_cell_class(name), "")

    def test_buyout_amount_is_a_buyout(self):
        with_buyout = SimpleNamespace(buyout_amount=993800, can_buyout=True)
        without = SimpleNamespace(buyout_amount=None, can_buyout=False)
        flag_only = SimpleNamespace(buyout_amount=None, can_buyout=True)

        self.assertTrue(contract_has_buyout(with_buyout))
        self.assertFalse(contract_has_buyout(without))
        self.assertFalse(contract_has_buyout(flag_only))
        self.assertEqual(buyout_cell_class(with_buyout), BUYOUT_CELL_CLASS)
        self.assertEqual(buyout_cell_class(without), "")

    def test_roster_row_colors_only_options_and_a_buyout(self):
        row = player(
            contract=contract(
                years=[
                    year(1_000_000, GUARANTEED, "Guaranteed"),
                    year(2_000_000, CLUB_OPTION, "Club option"),
                    year(3_000_000, VESTING_OPTION, "Vesting option"),
                    year(4_000_000, PLAYER_OPTION, "Player option or opt-out"),
                    year(500_000, PRE_ARB_0, "Pre-arbitration, 0.000–0.171"),
                    year(600_000, ARBITRATION, "Arbitration"),
                    {"amount": "-", "salary_class": "", "salary_label": ""},
                    {"amount": "-", "salary_class": "", "salary_label": ""},
                ],
                buyout_amount=250000,
            )
        )
        html = render_to_string(
            "includes/player_row.html",
            {"p": row, "team": True, "user": AnonymousUser()},
        )

        self.assertIn('class="salary-club_option"', html)
        self.assertIn('title="Club option"', html)
        self.assertIn('class="salary-vesting_option"', html)
        self.assertIn('title="Vesting option"', html)
        self.assertIn('class="salary-player_option"', html)
        self.assertIn('class="salary-buyout"', html)
        self.assertIn("$250,000", html)
        self.assertNotIn("salary-guaranteed", html)
        self.assertNotIn("salary-pre_arb_0", html)
        self.assertNotIn("salary-arbitration", html)

        plain = player(contract=contract(years=row.contract.years, buyout_amount=None))
        plain_html = render_to_string(
            "includes/player_row.html",
            {"p": plain, "team": True, "user": AnonymousUser()},
        )
        self.assertNotIn("salary-buyout", plain_html)
        self.assertIn("—", plain_html)

    def test_team_page_has_one_color_key_and_a_buyout_column(self):
        request = RequestFactory().get("/teams/durham/")
        request.user = AnonymousUser()
        row = player(contract=None)
        html = render_to_string(
            "team.html",
            {
                "team": SimpleNamespace(
                    name="Durham",
                    league=None,
                    division=None,
                    mlb_payroll=0,
                    cap_space=0,
                    pending_cap_after=None,
                    carried_salary=0,
                    cash=0,
                    pending_cash_after=None,
                    cash_borrowing=0,
                    ifa=0,
                    pending_ifa_after=None,
                    luxury_cap_space=0,
                ),
                "owners": [],
                "viewer_owns": False,
                "pending_player_count": 0,
                "total_count": 1,
                "roster_40_man_count": 1,
                "pos_counts": {"C": 0, "IF": 0, "OF": 0, "P": 1},
                "roster_sections": [
                    {"anchor": "mlb", "title": "MLB Roster", "players": [row]},
                ],
                "all_teams": [],
            },
            request=request,
        )
        self.assertEqual(html.count('class="salary-key'), 1)
        self.assertIn(">Club option<", html)
        self.assertIn(">Vesting option<", html)
        self.assertIn(">Player option<", html)
        self.assertIn(">Buyout<", html)
        self.assertIn('colspan="17"', html)
        self.assertIn("<td>—</td>", html)
