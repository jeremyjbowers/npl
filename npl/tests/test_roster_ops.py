"""Midseason nominations, roster limits, citations, impact, and the debut check."""

import datetime
from types import SimpleNamespace

import pytz
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from npl.admin import TransactionAdminForm
from npl.auctions import NominationError, nominate_player
from npl.mlbwatch import apply_person, hitting_stats, pitching_stats, refresh_appearances, store_splits
from npl.models import Auction, Owner, Player, Season, Team, Transaction, TransactionType
from npl.transactions.impact import counts_on_forty, impact_lines, obligation_lines
from npl.transactions.service import TransactionError, create_proposal, execute_proposal

User = get_user_model()


def _body(**kwargs):
    base = dict(
        roster_40man=False,
        roster_eosIL=False,
        roster_foreign=False,
        roster_retired=False,
        team_id=1,
        name="Player",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class RosterMathTests(TestCase):
    def test_forty_one_on_the_forty_man_must_remove_one(self):
        players = [_body(roster_40man=True) for _ in range(41)]
        forty = sum(1 for player in players if counts_on_forty(player))
        lines = obligation_lines("Alpha", forty, forty)
        self.assertEqual(len(lines), 1)
        self.assertIn("41 players on the 40-man", lines[0])
        self.assertIn("must remove 1", lines[0])
        self.assertIn("end-of-season IL", lines[0])

    def test_eighty_seven_on_the_reserve_list_must_drop_two(self):
        lines = obligation_lines("Alpha", 40, 87)
        self.assertEqual(len(lines), 1)
        self.assertIn("87 players on the 85-man", lines[0])
        self.assertIn("drop or reclassify 2", lines[0])

    def test_end_of_season_il_does_not_count_on_either_list(self):
        player = _body(roster_40man=True, roster_eosIL=True)
        self.assertFalse(counts_on_forty(player))
        from npl.transactions.impact import counts_on_reserve

        self.assertFalse(counts_on_reserve(player))

    def test_release_describes_cap_and_roster_space(self):
        team = Team.objects.create(full_name="Alpha Club", short_name="Alpha", abbreviation="ALP")
        player = _body(roster_40man=True, team_id=team.id, name="Trea Turner")
        player.team_id = team.id
        lines = impact_lines(
            "release",
            team,
            [{"asset_type": "player", "player": player, "from_team": team, "amount": None}],
        )
        text = " ".join(lines)
        self.assertIn("removes 1 player from the 40-man", text)
        self.assertIn("removes 1 player from the 85-man", text)


class CitationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cite@example.com", password="secret")
        self.owner = Owner.objects.create(name="Cite", user=self.user)
        self.team = Team.objects.create(full_name="Cite Club", short_name="Cite", abbreviation="CIT")
        self.team.owners.add(self.owner)
        self.player = Player.objects.create(
            mlb_id="500001",
            name="Hurt Player",
            first_name="Hurt",
            last_name="Player",
            team=self.team,
            roster_40man=True,
        )
        Season.objects.create(year=2026, phase=Season.REGULAR, is_current=True)

    def test_end_of_season_il_requires_a_url(self):
        with self.assertRaises(TransactionError) as caught:
            create_proposal(
                user=self.user,
                team=self.team,
                code="il_eos",
                assets=[{"asset_type": "player", "player": self.player}],
            )
        self.assertIn("URL", str(caught.exception))

        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="il_eos",
            assets=[{"asset_type": "player", "player": self.player}],
            notes="Out for the year. https://www.mlb.com/news/hurt-player-surgery",
        )
        self.assertEqual(proposal.kind, "il_eos")
        text = " ".join(
            __import__("npl.transactions.impact", fromlist=["lines_for_proposal"]).lines_for_proposal(proposal)
        )
        self.assertIn("end-of-season IL", text)
        self.assertIn("40-man", text)

    def test_foreign_list_requires_a_url(self):
        with self.assertRaises(TransactionError):
            create_proposal(
                user=self.user,
                team=self.team,
                code="foreign_place",
                assets=[{"asset_type": "player", "player": self.player}],
                notes="He went overseas.",
            )
        create_proposal(
            user=self.user,
            team=self.team,
            code="foreign_place",
            assets=[{"asset_type": "player", "player": self.player}],
            contract_terms={"source_url": "https://npb.jp/example"},
        )


class NominationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nom@example.com", password="secret")
        self.owner = Owner.objects.create(name="Nom", user=self.user)
        self.team = Team.objects.create(full_name="Nom Club", short_name="Nom", abbreviation="NOM")
        self.team.owners.add(self.owner)
        self.veteran = Player.objects.create(
            mlb_id="600001",
            name="Veteran Hitter",
            first_name="Veteran",
            last_name="Hitter",
            has_appeared_in_majors=True,
            mlb_debut_date=datetime.date(2018, 3, 29),
        )
        self.prospect = Player.objects.create(
            mlb_id="600002",
            name="Prospect Arm",
            first_name="Prospect",
            last_name="Arm",
            has_appeared_in_majors=False,
        )
        self.season = Season.objects.create(year=2026, phase=Season.REGULAR, is_current=True)
        self.client.force_login(self.user)

    def test_one_click_puts_a_debuted_free_agent_on_fridays_auction(self):
        response = self.client.post("/api/v1/players/600001/nominate/?kind=fa")
        self.assertTrue(response.json()["success"])
        self.assertIn("second-highest bid", response.json()["message"])
        auction = Auction.objects.get(player=self.veteran)
        self.assertTrue(auction.active)
        self.assertFalse(auction.is_nomination)
        self.assertEqual(auction.auction_kind, Auction.IN_SEASON)
        closes = auction.closes.astimezone(pytz.timezone("US/Eastern"))
        self.assertEqual(closes.hour, 15)
        self.assertEqual(closes.weekday(), 4)
        self.assertEqual(auction.nomination_details.nominating_team_id, self.team.id)

    def test_a_player_who_has_not_debuted_cannot_be_nominated_for_free_agency(self):
        response = self.client.post("/api/v1/players/600002/nominate/?kind=fa")
        self.assertFalse(response.json()["success"])
        self.assertIn("has not appeared", response.json()["message"])
        self.assertFalse(Auction.objects.filter(player=self.prospect).exists())

        ifa = self.client.post("/api/v1/players/600002/nominate/?kind=ifa")
        self.assertTrue(ifa.json()["success"], ifa.json())
        auction = Auction.objects.get(player=self.prospect)
        self.assertEqual(auction.auction_kind, Auction.IFA)

    def test_search_grays_out_the_wrong_button(self):
        page = self.client.get("/players/search/?name=Prospect")
        self.assertContains(page, "This player has not appeared in the majors. Use the IFA nomination.")
        self.assertContains(page, ">IFA</button>")
        veteran = self.client.get("/players/search/?name=Veteran")
        self.assertContains(
            veteran,
            "This player has appeared in the majors. Use the free-agent nomination.",
        )

    def test_offseason_free_agent_nomination_is_refused(self):
        self.season.phase = Season.OFFSEASON
        self.season.save(update_fields=["phase"])
        with self.assertRaises(NominationError):
            nominate_player(self.team, self.veteran, "fa")


class AuditAndPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(email="dir@example.com", password="secret")
        self.owner = Owner.objects.create(name="Dir", user=self.user)
        self.team = Team.objects.create(full_name="Dir Club", short_name="Dir", abbreviation="DIR")
        self.team.owners.add(self.owner)
        self.player = Player.objects.create(
            mlb_id="700001",
            name="Ledger Player",
            first_name="Ledger",
            last_name="Player",
            team=self.team,
            roster_40man=True,
        )
        self.kind = TransactionType.objects.get(code="release")
        Season.objects.create(year=2026, phase=Season.REGULAR, is_current=True)

    def test_a_change_requires_a_director_note(self):
        row = Transaction.objects.create(
            date=datetime.date(2026, 10, 13),
            team=self.team,
            player=self.player,
            transaction_type=self.kind,
            notes="original",
        )
        form = TransactionAdminForm(
            data={
                "date": "2026-10-13",
                "team": str(self.team.id),
                "player": self.player.mlb_id,
                "transaction_type": str(self.kind.id),
                "acquiring_team": "",
                "notes": "corrected acquiring club",
                "director_note": "",
                "cash_considerations": "",
                "mlb_id": "",
                "raw_player": "",
                "raw_team": "",
                "raw_acquiring_team": "",
                "raw_transaction_type": "",
            },
            instance=row,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("director_note", form.errors)

        form = TransactionAdminForm(
            data={
                "date": "2026-10-13",
                "team": str(self.team.id),
                "player": self.player.mlb_id,
                "transaction_type": str(self.kind.id),
                "acquiring_team": "",
                "notes": "corrected acquiring club",
                "director_note": "Sheet had the wrong club.",
                "cash_considerations": "",
                "mlb_id": "",
                "raw_player": "",
                "raw_team": "",
                "raw_acquiring_team": "",
                "raw_transaction_type": "",
            },
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_posting_a_proposal_stores_the_impact(self):
        proposal = create_proposal(
            user=self.user,
            team=self.team,
            code="release",
            assets=[{"asset_type": "player", "player": self.player}],
        )
        execute_proposal(self.user, proposal)
        row = Transaction.objects.get(proposal=proposal)
        self.assertIn("40-man", row.impact_summary)
        self.client.force_login(self.user)
        page = self.client.get("/transactions/")
        self.assertContains(page, row.impact_summary)
        roster = self.client.get(f"/teams/{self.team.short_name.lower()}/")
        self.assertContains(roster, 'class="sheet roster"')
        self.assertContains(roster, 'class="c-year"')

    def test_roster_check_page_names_an_over_full_forty_man(self):
        for number in range(40):
            Player.objects.create(
                mlb_id=f"8{number:05d}",
                name=f"Roster {number}",
                first_name="Roster",
                last_name=str(number),
                team=self.team,
                roster_40man=True,
            )
        page = self.client.get("/transactions/roundup/")
        self.assertContains(page, "must remove 1")
        self.assertContains(page, "Dir")


class DebutLoaderTests(TestCase):
    def test_people_payload_sets_debut_and_club(self):
        player = SimpleNamespace()
        apply_person(
            player,
            {"mlbDebutDate": "2018-03-29", "currentTeam": {"id": 147}},
            now=timezone.now(),
        )
        self.assertTrue(player.has_appeared_in_majors)
        self.assertEqual(player.mlb_debut_date, datetime.date(2018, 3, 29))
        self.assertEqual(player.mlb_org, "NYY")
        self.assertEqual(player.roster_status, "MLB")

        untouched = SimpleNamespace()
        apply_person(untouched, {"currentTeam": {"id": 431}}, now=timezone.now())
        self.assertFalse(untouched.has_appeared_in_majors)
        self.assertEqual(untouched.roster_status, "MINORS")

    def test_season_lines_use_the_mlb_id(self):
        player = Player.objects.create(mlb_id="592450", name="Aaron Judge", first_name="Aaron", last_name="Judge")
        row = hitting_stats(
            {
                "player": {"id": 592450},
                "stat": {"plateAppearances": 679, "homeRuns": 53, "avg": ".331", "gamesPlayed": 152},
            },
            2025,
        )
        self.assertEqual(row["slug"], "2025_majors_hit")
        self.assertEqual(row["hr"], 53)
        saved = store_splits(
            [{"player": {"id": 592450}, "stat": {"plateAppearances": 10, "homeRuns": 2, "gamesPlayed": 8}}],
            "hit",
            2025,
        )
        self.assertEqual(saved, 1)
        player.refresh_from_db()
        self.assertTrue(player.has_appeared_in_majors)
        self.assertEqual(player.stats["2025_majors_hit"]["hr"], 2)

        innings = pitching_stats(
            {"stat": {"gamesPitched": 30, "inningsPitched": "180.1", "strikeOuts": 200, "baseOnBalls": 40, "era": "2.50"}},
            2025,
        )
        self.assertEqual(innings["g"], 30)
        self.assertGreater(innings["k_9"], 9)

    def test_refresh_uses_the_supplied_payload(self):
        player = Player.objects.create(mlb_id="660271", name="Shohei Ohtani", first_name="Shohei", last_name="Ohtani")

        def getter(url):
            self.assertIn("660271", url)
            return {"people": [{"id": 660271, "mlbDebutDate": "2018-03-29", "currentTeam": {"id": 119}}]}

        self.assertEqual(refresh_appearances([player], getter=getter), 1)
        player.refresh_from_db()
        self.assertTrue(player.has_appeared_in_majors)
        self.assertEqual(player.mlb_org, "LAD")
