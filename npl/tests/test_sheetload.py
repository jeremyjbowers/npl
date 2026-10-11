"""Roster-sheet financials and contract colors, without a live workbook."""

import datetime
import unittest

from npl.sheetload import (
    ARBITRATION,
    CLUB_OPTION,
    Cell,
    GUARANTEED,
    PLAYER_OPTION,
    PRE_ARB_0,
    PRE_ARB_2,
    VESTING_OPTION,
    current_summary,
    league_minimum,
    parse_key_sheet,
    parse_money,
    parse_service_sheet,
    parse_team_sheet,
    salary_class,
    cash_is_overdrawn,
    settle_books,
)


def cell(value, bg=None, italic=False):
    return Cell(value, bg=bg, italic=italic)


def blank_row(width=22):
    return [cell("") for _ in range(width)]


def put(row, index, value, bg=None, italic=False):
    row[index] = cell(value, bg=bg, italic=italic)


class MoneyAndColorsTests(unittest.TestCase):
    def test_money_keeps_the_sign_and_ignores_words(self):
        self.assertEqual(parse_money("-$1,234,204"), -1234204)
        self.assertEqual(parse_money("$777,000"), 777000)
        self.assertEqual(parse_money("($5,000)"), -5000)
        self.assertIsNone(parse_money("NEVER GOES UNDER $0"))
        self.assertIsNone(parse_money(""))
        self.assertIsNone(parse_money("6th"))

    def test_legend_colors(self):
        self.assertEqual(salary_class(None), GUARANTEED)
        self.assertEqual(salary_class((255, 255, 255)), GUARANTEED)
        self.assertEqual(salary_class((255, 255, 0)), CLUB_OPTION)
        self.assertEqual(salary_class((255, 0, 0)), VESTING_OPTION)
        self.assertEqual(salary_class((180, 167, 214)), PLAYER_OPTION)
        self.assertEqual(salary_class((217, 234, 211)), PRE_ARB_0)
        self.assertEqual(salary_class((147, 196, 125)), PRE_ARB_2)
        self.assertEqual(salary_class((164, 194, 244)), ARBITRATION)

    def test_league_minimums_follow_the_cba_table(self):
        self.assertEqual(league_minimum(2026), 760000)
        self.assertEqual(league_minimum(2027), 780000)
        self.assertIsNone(league_minimum(2028))


class BooksTests(unittest.TestCase):
    def test_luxury_tax_is_paid_from_cash_and_is_not_refunded(self):
        under = settle_books(2_000_000, 0, cap_delta=-1_000_000)
        self.assertEqual(under["luxury_tax"], 0)
        self.assertEqual(under["cash_after"], 0)

        taxed = settle_books(0, 5_000_000, cap_delta=-1_000_000)
        self.assertEqual(taxed["luxury_tax"], 1_000_000)
        self.assertEqual(taxed["cash_after"], 4_000_000)
        self.assertLess(taxed["cap_after"], 0)

        broke = settle_books(0, 500_000, cap_delta=-1_000_000)
        self.assertLess(broke["cash_after"], 0)

        already = settle_books(-4_000_000, 1_000_000, cap_delta=-1_000_000)
        self.assertEqual(already["luxury_tax"], 1_000_000)
        self.assertEqual(already["cash_after"], 0)

        cut = settle_books(-4_000_000, 1_000_000, cap_delta=2_000_000)
        self.assertEqual(cut["luxury_tax"], 0)
        self.assertEqual(cut["cash_after"], 1_000_000)

        self.assertTrue(cash_is_overdrawn(500_000, broke["cash_after"]))
        self.assertFalse(cash_is_overdrawn(-1_234_204, -1_234_204))
        self.assertTrue(cash_is_overdrawn(-1_234_204, -1_334_204))


class TeamSheetTests(unittest.TestCase):
    def grid(self):
        rows = [blank_row() for _ in range(12)]
        put(rows[0], 10, "f. 2019")
        put(rows[2], 3, "PAYROLL")
        put(rows[2], 4, "CAP")
        put(rows[2], 5, "CASH")
        put(rows[2], 6, "LUXTAX")
        put(rows[2], 7, "85-MAN")
        put(rows[2], 8, "40-MAN")
        put(rows[3], 2, "2026")
        put(rows[3], 3, "$182,462,308")
        put(rows[3], 4, "$0")
        put(rows[3], 5, "-$1,234,204")
        put(rows[3], 6, "-$1,234,204")
        put(rows[3], 7, "83")
        put(rows[3], 8, "40")
        put(rows[4], 2, "2027")
        put(rows[4], 3, "$95,945,000")
        put(rows[4], 4, "$86,517,308")
        put(rows[4], 5, "$3,515,796")
        put(rows[4], 6, "NEVER GOES UNDER $0")
        for index, year in enumerate(range(2026, 2034)):
            put(rows[5], 9 + index, str(year))
        put(rows[5], 17, "BUYOUT")
        put(rows[5], 18, "CONTRACT TERMS")

        burke = blank_row()
        put(burke, 0, "1")
        put(burke, 1, "Burke, Sean")
        put(burke, 2, "39")
        put(burke, 3, "680732")
        put(burke, 4, "RHP")
        put(burke, 5, "CHW")
        put(burke, 6, "0.007")
        put(burke, 7, "3")
        put(burke, 9, "$777,000", bg=(217, 234, 211))
        rows.append(burke)

        minter = blank_row()
        put(minter, 0, "1")
        put(minter, 1, "Minter, A.J.", italic=True)
        put(minter, 2, "1342")
        put(minter, 3, "621345")
        put(minter, 6, "5.170")
        put(minter, 7, "99")
        put(minter, 8, "QO")
        put(minter, 9, "$5,300,000")
        put(minter, 10, "$6,625,000", bg=(255, 255, 0))
        put(minter, 17, "$993,800")
        put(minter, 18, "Offseason FA (2026)")
        rows.append(minter)

        gore = blank_row()
        put(gore, 0, "1")
        put(gore, 1, "Gore, MacKenzie")
        put(gore, 3, "669022")
        put(gore, 6, "3.090")
        put(gore, 9, "$4,880,000", bg=(255, 0, 0))
        put(gore, 10, "$7,320,000", bg=(180, 167, 214))
        put(gore, 18, "Extension", italic=True)
        rows.append(gore)

        rows.append(blank_row())
        financials = blank_row()
        put(financials, 1, "FINANCIALS")
        rows.append(financials)

        cap = blank_row()
        put(cap, 1, "SALARY CAP")
        for index, amount in enumerate(["$182,462,308", "$182,462,308", "$182,462,308"]):
            put(cap, 9 + index, amount)
        rows.append(cap)

        payroll = blank_row()
        put(payroll, 1, "TOTAL MAJOR LEAGUE PAYROLL")
        put(payroll, 9, "$182,462,308")
        put(payroll, 10, "$95,945,000")
        rows.append(payroll)

        reserves = blank_row()
        put(reserves, 1, "CASH RESERVES")
        put(reserves, 9, "-$1,234,204")
        put(reserves, 10, "$3,515,796")
        rows.append(reserves)

        section = blank_row()
        put(section, 1, "PAYROLL INCOME + EXPENDITURES")
        rows.append(section)

        carried = blank_row()
        put(carried, 1, "Nootbaar, Lars")
        put(carried, 4, "Carried salary by Villagers")
        put(carried, 9, "-$3,508,598")
        rows.append(carried)

        cash_header = blank_row()
        put(cash_header, 1, "CASH INCOME + EXPENDITURES")
        rows.append(cash_header)

        infusion = blank_row()
        put(infusion, 1, "NPL Distributed Funds")
        put(infusion, 9, "$5,250,000")
        put(infusion, 10, "$4,750,000")
        rows.append(infusion)

        penalty = blank_row()
        put(penalty, 1, "AAA AB/IP Penalties")
        put(penalty, 9, "$0")
        rows.append(penalty)

        ifa_header = blank_row()
        put(ifa_header, 1, "IFA CAP SPACE")
        rows.append(ifa_header)

        pool = blank_row()
        put(pool, 4, "Base:")
        put(pool, 5, "$4,750,000")
        put(pool, 6, "Can acquire:")
        put(pool, 7, "$8,312,500")
        put(pool, 8, "Total:")
        put(pool, 9, "$0")
        rows.append(pool)

        ifa_trade = blank_row()
        put(ifa_trade, 1, "5/25/2026")
        put(ifa_trade, 4, "Bears > Villagers")
        put(ifa_trade, 9, "-$1,000,000")
        rows.append(ifa_trade)

        draft = blank_row()
        put(draft, 1, "DRAFT PICK TRADES")
        rows.append(draft)
        pick = blank_row()
        put(pick, 1, "5/25/2026")
        put(pick, 4, "Bears > Ducksnorts")
        put(pick, 9, "6th")
        rows.append(pick)
        return rows

    def test_team_tab_maps_salaries_buyouts_and_the_ledger(self):
        parsed = parse_team_sheet(self.grid())
        self.assertEqual(parsed["founded"], 2019)
        books = current_summary(parsed, 2026)
        self.assertEqual(books["payroll"], 182462308)
        self.assertEqual(books["cap_space"], 0)
        self.assertEqual(books["cash"], -1234204)
        self.assertEqual(books["luxury"], -1234204)
        self.assertEqual(books["roster_85"], 83)
        self.assertIsNone(current_summary(parsed, 2027)["luxury"])

        by_name = {player["name"]: player for player in parsed["players"]}
        burke = by_name["Burke, Sean"]
        self.assertEqual(burke["mlb_id"], "680732")
        self.assertEqual(burke["mls"], "0.007")
        self.assertEqual(burke["years"], [
            {"year": 2026, "amount": 777000, "salary_class": PRE_ARB_0, "italic": False}
        ])

        minter = by_name["Minter, A.J."]
        self.assertTrue(minter["name_italic"])
        self.assertEqual(minter["sta"], "QO")
        self.assertEqual(minter["options"], "99")
        self.assertEqual(minter["buyout"], 993800)
        self.assertEqual(minter["terms"], "Offseason FA (2026)")
        self.assertEqual(minter["years"][0]["salary_class"], GUARANTEED)
        self.assertEqual(minter["years"][1]["salary_class"], CLUB_OPTION)
        self.assertEqual(minter["years"][1]["amount"], 6625000)

        gore = by_name["Gore, MacKenzie"]
        self.assertEqual(gore["years"][0]["salary_class"], VESTING_OPTION)
        self.assertEqual(gore["years"][1]["salary_class"], PLAYER_OPTION)
        self.assertTrue(gore["terms_pending"])

        self.assertEqual(parsed["projections"][2026]["salary_cap"], 182462308)
        self.assertEqual(parsed["projections"][2026]["payroll"], 182462308)
        self.assertEqual(parsed["projections"][2026]["cash"], -1234204)
        self.assertEqual(parsed["projections"][2027]["payroll"], 95945000)

        kinds = {(line["label"], line["book"], line["year"], line["amount"]) for line in parsed["lines"]}
        self.assertIn(("Nootbaar, Lars", "payroll", 2026, -3508598), kinds)
        self.assertEqual(
            next(line for line in parsed["lines"] if line["label"] == "Nootbaar, Lars")["detail"],
            "Carried salary by Villagers",
        )
        self.assertIn(("NPL Distributed Funds", "cash", 2026, 5250000), kinds)
        self.assertIn(("NPL Distributed Funds", "cash", 2027, 4750000), kinds)
        self.assertIn(("AAA AB/IP Penalties", "cash", 2026, 0), kinds)
        self.assertIn(("5/25/2026", "ifa", 2026, -1000000), kinds)
        self.assertIn(("Base", "ifa", 2026, 4750000), kinds)
        self.assertIn(("Can acquire", "ifa", 2026, 8312500), kinds)
        self.assertIn(("Total", "ifa", 2026, 0), kinds)
        self.assertFalse(any("Ducksnorts" in line["detail"] for line in parsed["lines"]))


class KeyAndServiceTests(unittest.TestCase):
    def test_key_tab_season_and_clubs(self):
        rows = [
            ["", "", "", "", "", "", "2026 Salary Cap", "$182,462,308"],
            ["", "", "", "", "", "", "2026 End of IFA", "3/8/2026"],
            ["", "", "", "", "", "", "2026 EOS", "11/15/2026"],
            ["NL: SAY HEY KID DIVISION", "", "85-Man", "40-Man", "30-Man", "Cap Space", "$ Reserves", "IFA Pool Space"],
            ["Honolulu Hitmen", "", "82", "40", "33", "$2,297,935", "$7,714,724", "$4,000,000"],
        ]
        parsed = parse_key_sheet(rows)
        self.assertEqual(parsed["season"]["year"], 2026)
        self.assertEqual(parsed["season"]["salary_cap"], 182462308)
        self.assertEqual(parsed["season"]["league_min"], 760000)
        self.assertEqual(parsed["season"]["ifa_deadline"], datetime.date(2026, 3, 8))
        self.assertEqual(parsed["season"]["end_of_season"], datetime.date(2026, 11, 15))
        self.assertEqual(len(parsed["teams"]), 1)
        hitmen = parsed["teams"][0]
        self.assertEqual(hitmen["full_name"], "Honolulu Hitmen")
        self.assertEqual(hitmen["roster_85"], 82)
        self.assertEqual(hitmen["cap_space"], 2297935)
        self.assertEqual(hitmen["cash"], 7714724)
        self.assertEqual(hitmen["ifa"], 4000000)

    def test_service_time_days(self):
        rows = [[
            "Name", "SS#", "MLB#", "POS", "MLB", "MLS", "OPT", "STA", "Team",
            "Option Used?", "Error?", "Missing SOS Service?",
            "MLB Days", "Option Days", "NR Days", "SOS Service Years", "SOS Service Days",
        ], [
            "Ashcraft, Braxton", "1212", "677952", "RHP", "PIT", "0.028", "3", "", "1",
            "FALSE", "FALSE", "FALSE", "28", "0", "159", "0", "0",
        ]]
        records = parse_service_sheet(rows)
        self.assertEqual(len(records), 1)
        row = records[0]
        self.assertEqual(row["mlb_id"], "677952")
        self.assertEqual(row["mls"], "0.028")
        self.assertFalse(row["option_used"])
        self.assertEqual(row["mlb_days"], 28)
        self.assertEqual(row["nonroster_days"], 159)
        self.assertEqual(row["sos_service_years"], 0)


if __name__ == "__main__":
    unittest.main()
