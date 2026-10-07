# The National Pastime League

## basics
* install virtualenv
* install virtualenvwrapper
* install postgres (I use postgres.app) and the command-line tools

## next
### pull down the repo
```
git clone git@github.com:jeremyjbowers/npl.git
```
### set up your django env
```cd npl
mkvirtualenv npl
add2virtualenv .
add2virtualenv config
add2virtualenv npl
export DJANGO_SETTINGS_MODULE=config.dev.settings
```
### install requirements
```
pip install -r requirements.txt
```

### load initial data
```
createdb npl
psql npl < npl.sql
```

### run the server
```
django-admin runserver
```

You'll be able to see this at `http://127.0.0.1:8000`.

I recommend editing your `/etc/hosts` to add a line like this:
```
127.0.0.1   localhost.nationalpastime.org
```

Then you can see the site at `http://localhost.nationalpastime.org:8000` in your browser.

## exporting the roster sheet to JSON

`util_export_rosters_json` boils the team tabs of the roster spreadsheet
(`settings.ROSTER_SHEET_ID`) down to one JSON document. It downloads the
sheet as **xlsx** rather than reading it through the Sheets values API,
because the sheet encodes contract type as cell colour (club option, vesting
option, player option, pre-arb tier, arbitration) and "salary covered by
another team" as italics, and only the xlsx export keeps that. No Google
credentials are needed as long as the sheet is link-viewable.

```
django-admin util_export_rosters_json                 # -> data/rosters/npl_rosters.json
django-admin util_export_rosters_json --per-team      # also data/rosters/npl_<team>.json
django-admin util_export_rosters_json --file x.xlsx   # parse a saved export instead
django-admin util_export_rosters_json --tab "Bulldog #18"
```

The parser itself is `npl/rosters.py` (no Django dependency); tests live in
`npl/tests/test_rosters.py` and run with `python -m unittest npl.tests.test_rosters`.

`initial_load_contracts` is built on the same parser, so every `ContractYear`
now carries `salary_type` (club / vesting / player option, pre-arb tier,
arbitration) and `is_covered`. It accepts `--file` and `--dry-run` too, and
matches teams to tabs by the trailing `#N` team number when a tab has been
renamed since `Team.tab_id` was set.

Output shape (abridged):

```json
{
  "generated": "2026-10-07T18:00:00+00:00",
  "warnings": ["MLB id 695445 listed on multiple teams: ..."],
  "teams": [
    {
      "tab": "Bulldog #18",
      "team": {"name": "Los Angeles Bulldog", "league": "AMERICAN LEAGUE", "division": "OIL CAN DIVISION",
               "founded": 2009, "staff": [{"title": "Co-General Manager", "name": "...", "email": "..."}],
               "seasons": {"2026": {"payroll": 182462308, "cap_space": 0, "cash": 3315526, "luxury_tax_space": 3315526}},
               "roster_counts": {"85_man": 83, "40_man": 40, "30_man": 33},
               "affiliates": {"AAA": "UNIVERSAL BASEBALL ASSOCIATION", "AA": "...", "A": "..."}},
      "salary_years": [2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033],
      "players": [
        {
          "mlb_id": 641487, "name": "Crawford, J.P.", "first_name": "J.P.", "last_name": "Crawford",
          "scoresheet_id": 560, "position": "SS", "mlb_org": "SEA",
          "level": "MLB", "roster_section": "active", "roster_subsection": null, "position_group": "INFIELDERS",
          "on_40_man": true, "roster_flag": "1",
          "service_time": {"raw": "6.157", "years": 6, "days": 157}, "eligible_year": null,
          "options": 99, "status": null,
          "salaries": [
            {"year": 2026, "amount": 8780000, "type": "guaranteed", "covered": true, "fill": null},
            {"year": 2028, "amount": 13696800, "type": "vesting_option", "covered": false, "fill": "FFFF0000"}
          ],
          "buyout": 2739400, "contract_terms": "vests with 450 ABs in 2027", "notes": [],
          "recall_date": null, "signed_as_offseason_fa": false, "flags": []
        }
      ],
      "financials": {"summary": {"SALARY CAP": {"2026": 182462308}}, "liabilities": [], "cash_ledger": [], "ifa": {}}
    }
  ]
}
```

Field notes:

* `mlb_id` is the MLBAM id and the key to join on. It is unique within a team;
  a player listed on two tabs is reported in `warnings`, not dropped.
* `level` uses the `Player.player_level` vocabulary (`MLB`, `IL`, `Restricted`,
  `AAA`, `AA`, `A`); `roster_section` is the sheet section
  (`active`, `7_day_il`, `56_day_il`, `eos_il`, `restricted`, `aaa`, `aa`, `a`)
  and `roster_subsection` the TRIPLE-A bucket (`on_option`, `assigned_outright`,
  `foreign`, `retired`, `non_roster`).
* `service_time` is `y.ddd` split out; for AA/A prospects the MLS column holds
  the year they become recall-eligible instead, which lands in `eligible_year`.
* `options` is options remaining; `99` is the sheet's "no longer optionable".
* `status` is the STA column: `QO`, `R5`, `OR`, `ORFA`.
* `salaries[].type` is decoded from the cell fill: `guaranteed` (no fill),
  `club_option`, `vesting_option`, `player_option` (incl. opt-outs),
  `pre_arb_0` / `pre_arb_1` / `pre_arb_2`, `arbitration`, or `unknown`. The raw
  `fill` hex is kept. `covered` is the italic "salary covered elsewhere" mark;
  the matching entries are in `financials.liabilities`.
* `signed_as_offseason_fa` is the italic-name mark (no trades before 6/1).
  `flags` carries row highlights: `recall_ineligible`, `pending_free_agent`,
  `pending_contract_terms`.
* Amounts are ints when whole dollars and floats when the sheet carries
  fractional dollars (some arbitration figures do).