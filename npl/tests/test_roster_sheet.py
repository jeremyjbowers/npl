"""Roster workbook parsing and the opening snapshot load."""

import csv
from pathlib import Path

from django.test import TestCase

from npl.models import (
    Contract,
    ContractYear,
    Player,
    Team,
    TeamFinancialLine,
    TeamLedgerYear,
)
from npl.sheet_load import apply_owners, apply_team_sheet
from npl.sheet_parse import parse_owners_sheet, parse_team_sheet
from users.models import User

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read_csv(name):
    with (FIXTURES / name).open(newline="") as handle:
        return list(csv.reader(handle))


def mini_sheet():
    return [
        ["CHEESEQUAKE CHEDDAR", "", "", "", "AMERICAN LEAGUE\nSULTAN OF SWAT DIVISION", "", "", "", "", "", "f. 2015"],
        ["", "", "", "", "", "", "PAYROLL", "", "", "CAP", "CASH", "LUXTAX", "85-MAN", "40-MAN", "Co-General Manager: Bret Sayre (bret.sayre@gmail.com)"],
        ["", "", "", "", "2026", "", "$10", "", "", "$4", "$3", "$2", "80", "30"],
        ["", "", "", "", "2027", "", "$9", "", "", "$8", "$5", "NEVER GOES UNDER $0", "30-MAN", "31"],
        ["", "", "", "", "POS", "MLB", "MLS", "OPT", "STA", "2026", "2027", "BUYOUT", "CONTRACT TERMS"],
        ["", "ACTIVE ROSTER"],
        ["1", "Baz, Shane", "22", "669358", "RHP", "BAL", "3.085", "2", "", "$100", "$200", "", "Extension"],
        ["1", "Stewart, Brock", "1296", "592779", "RHP", "LAD", "4.121", "0", "OR", "$50"],
        ["", "END OF SEASON INJURED LIST"],
        ["", "Garcia, Adolis", "1627", "666969", "OF", "PHI", "4.023", "3", "", "$80"],
        ["", "DOUBLE-A FORKED RIVER FISH"],
        ["-", "Osorio, Javier", "-", "703157", "SS", "DET", "2026"],
        ["-", "No Id, Player", "-", "-", "OF", "FA", "2028"],
        ["", "FINANCIALS"],
        ["", "SALARY CAP", "", "", "", "", "", "", "", "$1000", "$1000"],
        ["", "TOTAL MAJOR LEAGUE PAYROLL", "", "", "", "", "", "", "", "$10", "$9"],
        ["", "TOTAL AVAILABLE MAJOR LEAGUE CAP SPACE", "", "", "", "", "", "", "", "$4", "$8"],
        ["", "CASH RESERVES", "", "", "", "", "", "", "", "$3", "$5"],
        ["", "IFA CAP SPACE"],
        ["", "", "", "", "Base:", "", "$4,750,000", "", "", "Can acquire:", "$100", "Total:", "$4,750,000"],
        ["", "PAYROLL INCOME + EXPENDITURES"],
        ["", "$ Reserves Liabilities"],
        ["", "McNeil, Jeff", "", "", "Carried Salary by Guys", "", "", "", "", "-$300", "-$400"],
        ["", "CASH INCOME + EXPENDITURES"],
        ["", "Carried $ Reserves (Prior Seasons)", "", "", "", "", "", "", "", "$50", "$60"],
        ["", "Trade", "", "", "GmbH > Cheddar", "", "", "", "", "$25"],
    ]


class ParserTests(TestCase):
    def test_mini_sheet_uses_mlb_ids_and_reads_money(self):
        parsed = parse_team_sheet(mini_sheet())
        ids = [player["mlb_id"] for player in parsed["players"]]
        self.assertEqual(ids, ["669358", "592779", "666969", "703157"])
        self.assertEqual(parsed["unresolved"], [{"raw_name": "No Id, Player", "mlb_id": "-", "reason": "row has no MLB ID"}])

        baz = parsed["players"][0]
        self.assertEqual(baz["contract"]["years"], [{"year": 2026, "amount": 100}, {"year": 2027, "amount": 200}])
        self.assertEqual(baz["contract"]["notes"], "Extension")
        self.assertTrue(baz["flags"]["roster_40man"])
        self.assertTrue(baz["flags"]["roster_30man"])
        self.assertEqual(parsed["players"][1]["options"], 0)
        self.assertEqual(parsed["players"][1]["sta"], "OR")

        garcia = parsed["players"][2]
        self.assertEqual(garcia["section"], "eos")
        self.assertFalse(garcia["on_40"])
        self.assertTrue(garcia["flags"]["roster_eosIL"])

        osorio = parsed["players"][3]
        self.assertEqual(osorio["mls_year"], "2026")
        self.assertEqual(osorio["mls_time"], "")
        self.assertEqual(osorio["section"], "aa")
        self.assertEqual(parsed["farms"]["double_a"], "Forked River Fish")

        carried = [line for line in parsed["lines"] if line["kind"] == "carried_salary"]
        self.assertEqual([(line["year"], line["amount"], line["counterparty"]) for line in carried], [
            (2026, -300, "Guys"),
            (2027, -400, "Guys"),
        ])
        reserves = [line for line in parsed["lines"] if line["label"].startswith("Carried $")]
        self.assertEqual(reserves[0]["kind"], "cash_reserves")
        self.assertEqual(parsed["ledger"][1]["luxury_note"], "NEVER GOES UNDER $0")
        self.assertEqual(parsed["ledger"][0]["ifa_total"], 4750000)
        self.assertEqual(parsed["managers"][0]["email"], "bret.sayre@gmail.com")
        plain = parse_team_sheet([
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "General Manager: Smith Brickner (smithbrickner@gmail.com)"],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "GM: Michael Wagner (michaelcw96@gmail.com)"],
            ["", "Co-Owner: Gina (gdegraph@gmail.com)"],
            ["", "ACTIVE ROSTER"],
            ["", "Ignore: Somebody (not-a-person@example.com)"],
        ])
        emails = {manager["email"]: manager["title"] for manager in plain["managers"]}
        self.assertEqual(emails["smithbrickner@gmail.com"], "General Manager")
        self.assertEqual(emails["michaelcw96@gmail.com"], "GM")
        self.assertEqual(emails["gdegraph@gmail.com"], "Co-Owner")
        self.assertNotIn("not-a-person@example.com", emails)
        self.assertEqual(parsed["full_name"], "Cheesequake Cheddar")
        self.assertEqual(parsed["league"], "AL")
        self.assertEqual(parsed["founded"], 2015)

    def test_cheddar_fixture_keeps_mlb_ids_and_carried_salary(self):
        parsed = parse_team_sheet(read_csv("cheddar.csv"))
        self.assertGreater(len(parsed["players"]), 40)
        self.assertTrue(all(player["mlb_id"].isdigit() for player in parsed["players"]))
        self.assertFalse(any(item["reason"] == "row has no MLB ID" for item in parsed["unresolved"]))

        baz = next(player for player in parsed["players"] if player["mlb_id"] == "669358")
        self.assertEqual(baz["first_name"], "Shane")
        self.assertEqual(baz["last_name"], "Baz")
        self.assertEqual(baz["contract"]["years"][0], {"year": 2026, "amount": 2474616})
        stewart = next(player for player in parsed["players"] if player["mlb_id"] == "592779")
        self.assertEqual(stewart["options"], 0)

        garcia = next(player for player in parsed["players"] if player["mlb_id"] == "666969")
        self.assertEqual(garcia["section"], "eos")
        self.assertFalse(garcia["on_40"])

        mcneil = [line for line in parsed["lines"] if line["player_name"] == "McNeil, Jeff"]
        self.assertEqual([line["amount"] for line in mcneil], [-3000000, -3000000])
        self.assertTrue(all(line["kind"] == "carried_salary" for line in mcneil))
        self.assertEqual(parsed["ledger"][0]["payroll"], 181697033)
        self.assertEqual(parsed["ledger"][0]["ifa_total"], 4750000)
        emails = {manager["email"] for manager in parsed["managers"]}
        self.assertIn("bret.sayre@gmail.com", emails)
        self.assertIn("harrypav@gmail.com", emails)

    def test_bears_carried_salary_includes_short_labels(self):
        parsed = parse_team_sheet(read_csv("bears.csv"))
        carried = [line for line in parsed["lines"] if line["kind"] == "carried_salary" and line["year"] == 2026]
        by_name = {line["player_name"]: line for line in carried}
        self.assertEqual(by_name["Gore, MacKenzie"]["counterparty"], "GmbH")
        self.assertEqual(by_name["Gore, MacKenzie"]["amount"], -4880000)
        self.assertEqual(by_name["Chapman, Aroldis"]["amount"], 10750000)
        reserves = [line for line in parsed["lines"] if "Reserves" in line["label"]]
        self.assertTrue(reserves)
        self.assertTrue(all(line["kind"] != "carried_salary" for line in reserves))

    def test_owners_sheet_carries_the_team_forward(self):
        people = parse_owners_sheet(read_csv("owners.csv"))
        by_email = {person["email"]: person for person in people}
        self.assertEqual(by_email["harrypav@gmail.com"]["team_label"], "Cheesequake Cheddar")
        self.assertEqual(by_email["grant.mail2@yahoo.com"]["team_label"], "Chicago Kodiaks")
        self.assertEqual(by_email["nplhitmen@gmail.com"]["team_label"], "Honolulu Hitmen")
        self.assertEqual(by_email["nplhitmen@gmail.com"]["name"], "TEAM")
        self.assertGreater(len(people), 40)
        self.assertTrue(all(person["email"] for person in people))


class LoadTests(TestCase):
    def test_apply_creates_players_contracts_and_carried_salary(self):
        Team.objects.create(full_name="Bad Guys", short_name="Guys")
        parsed = parse_team_sheet(mini_sheet())
        result = apply_team_sheet(parsed, "Cheddar #1", 2026)
        team = result["team"]
        self.assertEqual(team.short_name, "Cheddar")
        self.assertEqual(team.full_name, "Cheesequake Cheddar")
        self.assertEqual(team.tab_id, "Cheddar #1")
        self.assertEqual(team.initial_season, 2015)
        self.assertEqual(team.league.name, "AL")
        self.assertEqual(team.cap_space, 4)
        self.assertEqual(team.cash, 3)
        self.assertEqual(team.luxury_cap_space, 2)
        self.assertEqual(team.ifa, 4750000)
        self.assertEqual(team.carried_salary, -300)
        self.assertEqual(team.contract_salary, 10)
        self.assertEqual(team.double_a_name, "Forked River Fish")

        baz = Player.objects.get(mlb_id="669358")
        self.assertEqual(baz.team, team)
        self.assertEqual(baz.name, "Shane Baz")
        self.assertTrue(baz.roster_30man)
        self.assertTrue(baz.roster_40man)
        self.assertEqual(baz.player_level, "MLB")
        self.assertEqual(baz.contract.total_years, 2)
        self.assertEqual(
            list(ContractYear.objects.filter(contract=baz.contract).order_by("year").values_list("year", "amount")),
            [(2026, 100), (2027, 200)],
        )

        stewart = Player.objects.get(mlb_id="592779")
        self.assertEqual(stewart.options, 0)
        self.assertEqual(stewart.sta, "OR")

        garcia = Player.objects.get(mlb_id="666969")
        self.assertTrue(garcia.roster_eosIL)
        self.assertFalse(garcia.roster_40man)
        self.assertEqual(garcia.player_level, "IL")

        osorio = Player.objects.get(mlb_id="703157")
        self.assertEqual(osorio.mls_year, "2026")
        self.assertTrue(osorio.roster_doubleA)
        self.assertEqual(osorio.player_level, "AA")
        self.assertIsNone(osorio.contract)

        self.assertFalse(Player.objects.filter(raw_name="No Id, Player").exists())
        self.assertEqual(TeamLedgerYear.objects.filter(team=team).count(), 2)
        carried = TeamFinancialLine.objects.get(team=team, kind="carried_salary", year=2026)
        self.assertEqual(carried.amount, -300)
        self.assertEqual(carried.counterparty_team.short_name, "Guys")
        self.assertEqual(TeamFinancialLine.objects.filter(team=team, kind="cash_reserves").count(), 2)

        departed = Player.objects.create(mlb_id="1", name="Gone Player", team=team)
        apply_team_sheet(parsed, "Cheddar #1", 2026)
        departed.refresh_from_db()
        self.assertIsNone(departed.team_id)
        self.assertEqual(Contract.objects.filter(player=baz).count(), 1)
        self.assertEqual(TeamFinancialLine.objects.filter(team=team, kind="carried_salary").count(), 2)

    def test_owners_become_users_and_follow_manager_email(self):
        cheddar = Team.objects.create(short_name="Cheddar", full_name="Cheddar")
        king = Team.objects.create(short_name="King", full_name="Lion King")
        kodiaks = Team.objects.create(short_name="Kodiaks", full_name="Kodiaks")
        people = parse_owners_sheet(read_csv("owners.csv"))
        result = apply_owners(
            people,
            managers=[
                {
                    "email": "smithbrickner@gmail.com",
                    "name": "Smith Brickner",
                    "title": "General Manager",
                    "team": king,
                },
                {
                    "email": "mattwinkelman136@gmail.com",
                    "name": "Matt Winkelman",
                    "title": "Assistant General Manager",
                    "team": kodiaks,
                },
                {
                    "email": "bret.sayre@gmail.com",
                    "name": "Bret Sayre",
                    "title": "Co-General Manager",
                    "team": cheddar,
                },
                {
                    "email": "harry-desk@example.com",
                    "name": "Harry Pavlidis",
                    "title": "Co-General Manager",
                    "team": cheddar,
                },
            ],
        )
        bret = User.objects.get(email="bret.sayre@gmail.com")
        self.assertEqual(bret.owner.name, "Bret Sayre")
        self.assertEqual(bret.owner.title, "Co-General Manager")
        self.assertEqual(bret.owner.year_joined, 2015)
        cheddar.refresh_from_db()
        self.assertEqual(cheddar.full_name, "Cheesequake Cheddar")
        self.assertTrue(cheddar.owners.filter(email="harrypav@gmail.com").exists())
        self.assertEqual(User.objects.get(email="harrypav@gmail.com").owner.title, "Co-General Manager")

        smith = User.objects.get(email="smithbrickner@gmail.com")
        self.assertEqual(smith.owner.title, "General Manager")
        self.assertTrue(king.owners.filter(user=smith).exists())
        king.refresh_from_db()
        self.assertEqual(king.full_name, "Lion King")

        matt = User.objects.get(email="mattwinkelman136@gmail.com")
        self.assertEqual(matt.owner.title, "Assistant General Manager")
        self.assertTrue(kodiaks.owners.filter(user=matt).exists())
        self.assertFalse(matt.has_usable_password())

        self.assertIn("Absolute Sickos", result["unmatched_teams"])
        self.assertNotIn("Sound Hydra", result["unmatched_teams"])
        self.assertTrue(User.objects.filter(email="nplhitmen@gmail.com").exists())
