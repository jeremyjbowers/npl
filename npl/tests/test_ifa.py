"""International free-agent eligibility for the IFA nomination button."""

import datetime
from types import SimpleNamespace
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from npl import ifa
from npl.auctions import NominationError, nominate_player
from npl.mlbwatch import refresh_appearances
from npl.models import Contract, Owner, Player, Season, Team, Transaction, TransactionType

User = get_user_model()


def season(year=2026, phase="regular", deadline=None, opening=None):
    return SimpleNamespace(year=year, phase=phase, ifa_deadline=deadline, opening_day=opening)


def player(**kwargs):
    base = dict(
        name="Kid Player",
        mlb_id="1",
        has_appeared_in_majors=False,
        has_been_rostered=False,
        birthdate=datetime.date(2005, 4, 2),
        ifa_checked=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc),
        international_signee=True,
        international_signing_date=datetime.date(2024, 1, 15),
        international_mlb_contract=False,
        stateside_seasons=0,
        npb_kbo_seasons=0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class RuleTests(SimpleTestCase):
    def test_january_first_birthday_is_not_under_25(self):
        self.assertFalse(ifa.under_25(datetime.date(2002, 1, 1), 2027))
        self.assertTrue(ifa.under_25(datetime.date(2002, 1, 2), 2027))

    def test_ifa_year_uses_the_deadline_then_the_upcoming_season(self):
        today = datetime.date(2026, 10, 13)
        self.assertEqual(ifa.ifa_year(season(), today), 2027)
        self.assertEqual(
            ifa.ifa_year(season(deadline=datetime.date(2026, 3, 8)), datetime.date(2026, 2, 1)),
            2026,
        )
        self.assertEqual(
            ifa.ifa_year(season(deadline=datetime.date(2026, 3, 8)), today),
            2027,
        )
        self.assertEqual(
            ifa.ifa_year(
                season(phase="offseason", opening=datetime.date(2026, 3, 28)),
                datetime.date(2026, 1, 15),
            ),
            2026,
        )
        self.assertEqual(
            ifa.ifa_year(season(phase="offseason"), datetime.date(2026, 1, 15)),
            2026,
        )
        self.assertEqual(
            ifa.ifa_year(season(phase="offseason"), datetime.date(2026, 11, 1)),
            2027,
        )

    def test_dsl_does_not_count_and_a_second_stateside_year_does(self):
        dsl_only = [
            {"season": "2024", "sport": {"id": 16}, "league": {"id": 130}, "stat": {"gamesPlayed": 1}},
            {"season": "2025", "sport": {"id": 16}, "league": {"id": 130}, "stat": {"gamesPlayed": 1}},
            {"season": "2025", "sport": {"id": 16}, "league": {}, "stat": {"gamesPlayed": 18}},
        ]
        self.assertEqual(ifa.seasons_from_stats(dsl_only), (0, 0))

        two_years = [
            {"season": "2025", "sport": {"id": 16}, "league": {"id": 121}, "stat": {"gamesPlayed": 1}},
            {"season": "2026", "sport": {"id": 14}, "league": {"id": 110}, "stat": {"gamesPitched": 3}},
        ]
        self.assertEqual(ifa.seasons_from_stats(two_years), (2, 0))

        same_year = [
            {"season": "2026", "sport": {"id": 16}, "league": {"id": 124}, "stat": {"gamesPlayed": 2}},
            {"season": "2026", "sport": {"id": 13}, "league": {"id": 112}, "stat": {"gamesPlayed": 9}},
        ]
        self.assertEqual(ifa.seasons_from_stats(same_year), (1, 0))
        self.assertEqual(
            ifa.seasons_from_stats(
                [
                    {"season": "2022", "sport": {"id": 31}, "stat": {"gamesPlayed": 10}},
                    {"season": "2023", "sport": {"id": 32}, "stat": {"gamesPlayed": 10}},
                    {"season": "2024", "sport": {"id": 31}, "stat": {"gamesPlayed": 10}},
                ]
            ),
            (0, 3),
        )

    def test_signing_classification(self):
        minor = {
            "date": "2023-01-15",
            "typeCode": "SFA",
            "description": "Los Angeles Dodgers signed free agent OF Kid to a minor league contract.",
        }
        drafted = {
            "date": "2024-07-19",
            "typeCode": "SGN",
            "description": "Cleveland Guardians signed 2B Travis Bazzana.",
        }
        major = {
            "date": "2025-01-15",
            "typeCode": "SFA",
            "description": "Los Angeles Dodgers signed free agent P Ace to a major league contract.",
        }
        self.assertTrue(ifa.classify_signing([minor], "Venezuela")["international"])
        self.assertFalse(ifa.classify_signing([minor], "Venezuela")["major_league_contract"])
        self.assertFalse(ifa.classify_signing([drafted], "Australia")["international"])
        self.assertFalse(ifa.classify_signing([minor], "USA")["international"])
        japan = ifa.classify_signing([major], "Japan")
        self.assertTrue(japan["international"])
        self.assertTrue(japan["major_league_contract"])
        self.assertIsNone(ifa.classify_signing([minor], "")["international"])
        self.assertFalse(ifa.classify_signing([], "Cuba")["international"])
        first = ifa.classify_signing([major, drafted], "Japan")
        self.assertFalse(first["international"])
        self.assertEqual(first["date"], datetime.date(2024, 7, 19))

    def test_eligibility_accepts_one_stateside_year_and_rejects_the_rule_breaks(self):
        today = datetime.date(2026, 10, 13)
        current = season()
        ok, reason = ifa.eligibility(player(stateside_seasons=1), current, today)
        self.assertTrue(ok, reason)

        cases = [
            (dict(birthdate=datetime.date(1998, 5, 1)), "not under 25"),
            (dict(birthdate=None), "Birthdate is missing"),
            (dict(ifa_checked=None), "has not been checked"),
            (dict(international_signee=False), "not signed"),
            (dict(international_signee=None), "Birth country"),
            (dict(international_mlb_contract=True), "major-league contract"),
            (dict(international_signing_date=None), "no international signing date"),
            (dict(npb_kbo_seasons=3), "NPB or KBO"),
            (dict(stateside_seasons=2), "more than one calendar year"),
            (dict(has_appeared_in_majors=True), "appeared in the majors"),
            (dict(has_appeared_in_majors=None), "Majors debut has not been checked"),
        ]
        for overrides, snippet in cases:
            with self.subTest(snippet=snippet):
                eligible, why = ifa.eligibility(player(**overrides), current, today)
                self.assertFalse(eligible)
                self.assertIn(snippet, why)

        late = season(deadline=datetime.date(2026, 3, 8))
        eligible, why = ifa.eligibility(
            player(international_signing_date=datetime.date(2026, 4, 1)),
            late,
            datetime.date(2026, 2, 1),
        )
        self.assertFalse(eligible)
        self.assertIn("had not signed", why)


class ButtonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ifa@example.com", password="secret")
        self.owner = Owner.objects.create(name="IFA", user=self.user)
        self.team = Team.objects.create(full_name="IFA Club", short_name="Ifa", abbreviation="IFA")
        self.team.owners.add(self.owner)
        self.season = Season.objects.create(year=2026, phase=Season.REGULAR, is_current=True)
        self.client.force_login(self.user)

    def make(self, mlb_id, name, **kwargs):
        fields = dict(
            mlb_id=mlb_id,
            name=name,
            first_name=name.split()[0],
            last_name=name.split()[-1],
            has_appeared_in_majors=False,
            birthdate=datetime.date(2006, 3, 3),
            birth_country="Dominican Republic",
            stateside_seasons=0,
            npb_kbo_seasons=0,
            international_signee=True,
            international_signing_date=datetime.date(2024, 1, 15),
            international_mlb_contract=False,
            ifa_checked=timezone.now(),
        )
        fields.update(kwargs)
        return Player.objects.create(**fields)

    def test_the_button_is_shown_only_for_an_eligible_player(self):
        kid = self.make("610001", "Eligible Kid")
        self.make("610002", "Older Kid", birthdate=datetime.date(1990, 1, 1))
        self.make("610003", "Stateside Kid", stateside_seasons=2)
        self.make("610004", "Drafted Kid", international_signee=False)
        self.make("610005", "Unchecked Kid", ifa_checked=None)
        self.make("610006", "Major Deal", international_mlb_contract=True)
        self.make("610007", "Foreign Pro", npb_kbo_seasons=3)
        self.make("610008", "Rostered Kid", has_been_rostered=True)
        released = self.make("610009", "Released Kid")
        contracted = self.make("610010", "Contract Kid")
        Transaction.objects.create(
            date=datetime.date(2024, 6, 1),
            player=released,
            team=self.team,
            transaction_type=TransactionType.objects.get(code="release"),
            mlb_id=released.mlb_id,
        )
        Contract.objects.create(player=contracted, team=self.team)

        page = self.client.get(f"/players/{kid.mlb_id}/")
        self.assertContains(page, "Nominate for IFA")
        search = self.client.get("/players/search/?name=Eligible")
        self.assertContains(search, 'data-kind="ifa"')

        for mlb_id, snippet in (
            ("610002", "not under 25"),
            ("610003", "more than one calendar year"),
            ("610004", "not signed"),
            ("610005", "has not been checked"),
            ("610006", "major-league contract"),
            ("610007", "NPB or KBO"),
            ("610008", "Rule 4 draft"),
            ("610009", "Rule 4 draft"),
            ("610010", "Rule 4 draft"),
        ):
            with self.subTest(mlb_id=mlb_id):
                detail = self.client.get(f"/players/{mlb_id}/")
                self.assertNotContains(detail, "Nominate for IFA")
                self.assertContains(detail, snippet)
                response = self.client.post(f"/api/v1/players/{mlb_id}/nominate/?kind=ifa")
                self.assertFalse(response.json()["success"])
                self.assertIn(snippet, response.json()["message"])

    def test_offseason_keeps_the_button_visible_and_refuses_the_nomination(self):
        kid = self.make("610011", "Offseason Kid")
        self.season.phase = Season.OFFSEASON
        self.season.save(update_fields=["phase"])
        page = self.client.get(f"/players/{kid.mlb_id}/")
        self.assertContains(page, "Nominate for IFA")
        self.assertContains(page, "Offseason auctions are a separate process.")
        with self.assertRaises(NominationError):
            nominate_player(self.team, kid, "ifa")

    def test_refresh_stores_stateside_seasons_and_hides_the_button(self):
        kid = Player.objects.create(mlb_id="700010", name="Stats Kid", first_name="Stats", last_name="Kid")

        def getter(url):
            text = unquote(url)
            if "sportId=14" in text:
                return {
                    "people": [
                        {
                            "id": 700010,
                            "stats": [
                                {
                                    "splits": [
                                        {
                                            "season": "2024",
                                            "sport": {"id": 14},
                                            "league": {"id": 110},
                                            "stat": {"gamesPlayed": 8},
                                        },
                                        {
                                            "season": "2025",
                                            "sport": {"id": 14},
                                            "league": {"id": 110},
                                            "stat": {"gamesPlayed": 4},
                                        },
                                    ]
                                }
                            ],
                        }
                    ]
                }
            if "sportId=" in text:
                return {"people": [{"id": 700010, "stats": []}]}
            return {
                "people": [
                    {
                        "id": 700010,
                        "birthDate": "2004-06-01",
                        "birthCountry": "Venezuela",
                        "currentTeam": {"id": 431},
                        "transactions": [
                            {
                                "date": "2023-01-15",
                                "typeCode": "SFA",
                                "description": "Los Angeles Dodgers signed free agent OF Kid to a minor league contract.",
                            }
                        ],
                    }
                ]
            }

        self.assertEqual(refresh_appearances([kid], getter=getter), 1)
        kid.refresh_from_db()
        self.assertFalse(kid.has_appeared_in_majors)
        self.assertEqual(kid.birthdate, datetime.date(2004, 6, 1))
        self.assertEqual(kid.birth_country, "Venezuela")
        self.assertEqual(kid.stateside_seasons, 2)
        self.assertEqual(kid.npb_kbo_seasons, 0)
        self.assertTrue(kid.international_signee)
        self.assertEqual(kid.international_signing_date, datetime.date(2023, 1, 15))
        self.assertFalse(kid.international_mlb_contract)
        self.assertIsNotNone(kid.ifa_checked)
        page = self.client.get("/players/700010/")
        self.assertNotContains(page, "Nominate for IFA")
