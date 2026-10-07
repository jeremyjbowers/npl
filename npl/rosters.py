"""
Parse the NPL team roster spreadsheet (xlsx export) into plain dicts.

The roster sheet encodes a lot of information in cell *formatting* that the
Sheets values API throws away: salary cell fill colour is the contract type
(guaranteed / club option / vesting / pre-arb tier / arbitration ...), an
italic salary means the money is covered by another team, an italic name
means the player signed as an offseason free agent and can't be traded until
6/1. The xlsx export preserves all of that, so this module works from the
xlsx rather than from the values API used elsewhere in the repo.

Nothing in here imports Django; the management command
``util_export_rosters_json`` is the thin wrapper that fetches the workbook and
writes the output.

Layout of a team tab (0-indexed columns, matching utils.format_player_row):

    0  40-man flag ("1" on the 40-man, "-" otherwise)
    1  "Last, First"
    2  Scoresheet id
    3  MLB (MLBAM) id  <- the unique player key
    4  position
    5  MLB org
    6  MLS (major league service, "y.ddd") or, for AA/A kids, the year they
       become recall-eligible
    7  options remaining (99 == no longer optionable)
    8  status: QO / R5 / OR / ORFA
    9..16  salary for SALARY_YEARS[0] .. SALARY_YEARS[-1]
    17 buyout
    18 contract terms / notes
    19+ overflow notes
"""

import datetime
import io
import re

import openpyxl
import requests

EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

# Tabs in the workbook that are not team rosters.
NON_TEAM_TABS = {"Key", "IDs", "Service Time"}
NON_TEAM_TAB_RE = re.compile(r"^\d{4} Contracts$")

COL_FLAG = 0
COL_NAME = 1
COL_SS_ID = 2
COL_MLB_ID = 3
COL_POS = 4
COL_ORG = 5
COL_MLS = 6
COL_OPT = 7
COL_STA = 8
COL_SALARY_START = 9
COL_SALARY_END = 17  # exclusive
COL_BUYOUT = 17
COL_TERMS = 18
# The TRIPLE-A section header puts "RECALL DATE" over this column; for
# optioned players the cell holds a date rather than a 2030 salary.
COL_RECALL_DATE = 13

# Section headers that change which bucket subsequent player rows land in.
# ``level`` is the Player.player_level vocabulary used in npl.models.
LEVEL_SECTIONS = [
    (re.compile(r"^ACTIVE ROSTER$", re.I), "MLB", "active"),
    (re.compile(r"^7-DAY INJURED LIST$", re.I), "IL", "7_day_il"),
    (re.compile(r"^56-DAY INJURED LIST$", re.I), "IL", "56_day_il"),
    (re.compile(r"^END OF SEASON INJURED LIST$", re.I), "IL", "eos_il"),
    (re.compile(r"^RESTRICTED LIST$", re.I), "Restricted", "restricted"),
    (re.compile(r"^TRIPLE[- ]A\b", re.I), "AAA", "aaa"),
    (re.compile(r"^DOUBLE[- ]A\b", re.I), "AA", "aa"),
    (re.compile(r"^SINGLE[- ]A\b", re.I), "A", "a"),
]
# Sub-buckets inside TRIPLE-A.
AAA_SUBSECTIONS = {
    "ON OPTION": "on_option",
    "ASSIGNED OUTRIGHT": "assigned_outright",
    "FOREIGN": "foreign",
    "RETIRED": "retired",
    "NON-ROSTER": "non_roster",
}
# Position groupings inside ACTIVE ROSTER.
POSITION_GROUPS = {"STARTING PITCHERS", "RELIEF PITCHERS", "INFIELDERS", "OUTFIELDERS"}

FINANCIALS_HEADER = "FINANCIALS"

# Salary-cell fill -> contract type, from the swatches on the Key tab. GMs
# reach for neighbouring shades in the Google palette (light blue 3 instead of
# light cornflower blue 1, light magenta instead of light purple, ...), so a
# fill is classified by hue family and the raw hex is kept alongside.
#
#   yellow  -> club_option          red     -> vesting_option
#   purple / magenta -> player_option (or opt-out clause)
#   blue    -> arbitration          green   -> pre-arb tier (by shade)
SALARY_HUE_FAMILIES = [
    # (hue lower bound, hue upper bound, type); hue in degrees
    (35, 75, "club_option"),
    (75, 170, "pre_arb"),
    (170, 240, "arbitration"),
    (240, 340, "player_option"),
]
# Red wraps around 0.
SALARY_RED_FAMILY = (340, 20, "vesting_option")
# The three pre-arb tiers are the same green at different lightness.
PRE_ARB_SHADES = {
    "FFD9EAD3": "pre_arb_0",  # 0.000-0.171
    "FFB6D7A8": "pre_arb_1",  # 1.000-1.171
    "FF93C47D": "pre_arb_2",  # 2.000+
}
# Fills on the non-salary cells of a row (name, MLS, recall date ...).
ROW_FILL_LEGEND = {
    "FFF4C7C3": "recall_ineligible",
    "FF9900FF": "pending_free_agent",
    "FFB7B7B7": "pending_contract_terms",
}
NO_FILL = {None, "", "00000000", "FFFFFFFF", "FFFDFDFD"}
# Max RGB distance (0-441) for a row fill to be snapped to a legend colour.
COLOUR_SNAP_THRESHOLD = 30
# Below this HSV saturation a fill is treated as white/grey, not a colour.
MIN_SATURATION = 0.05

MONEY_RE = re.compile(r"^-?\$?[\d,]+(\.\d+)?$")
NAME_RE = re.compile(r"^[^,]+,\s*\S")


# ---------------------------------------------------------------------------
# small cell helpers


def cell_fill(cell):
    """ARGB hex of a cell's solid fill, or None if it has none."""
    fg = cell.fill.fgColor
    if fg is None or fg.type != "rgb":
        return None
    rgb = fg.rgb
    if not isinstance(rgb, str) or rgb in NO_FILL:
        return None
    return rgb.upper()


def _rgb(argb):
    return int(argb[2:4], 16), int(argb[4:6], 16), int(argb[6:8], 16)


def _rgb_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def _hue_saturation(argb):
    r, g, b = _rgb(argb)
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == 0 or hi == lo:
        return None, 0.0
    sat = (hi - lo) / hi
    if hi == r:
        hue = 60 * ((g - b) / (hi - lo)) % 360
    elif hi == g:
        hue = 60 * ((b - r) / (hi - lo)) + 120
    else:
        hue = 60 * ((r - g) / (hi - lo)) + 240
    return hue, sat


def nearest_legend_colour(argb, legend, threshold=COLOUR_SNAP_THRESHOLD):
    """Snap a fill to the closest legend entry, or None if nothing is close."""
    if argb is None:
        return None
    if argb in legend:
        return legend[argb]
    best, best_d = None, None
    for hexcode, meaning in legend.items():
        d = _rgb_distance(argb, hexcode)
        if best_d is None or d < best_d:
            best, best_d = meaning, d
    if best_d is not None and best_d <= threshold:
        return best
    return None


def salary_type_for_fill(argb):
    """
    Contract type for a salary cell's fill.

    None / white -> "guaranteed". A coloured fill is classified by hue family
    (see SALARY_HUE_FAMILIES); a colour outside every family returns
    "unknown" so the caller can warn without losing the raw hex.
    """
    if argb is None:
        return "guaranteed"
    hue, sat = _hue_saturation(argb)
    if hue is None or sat < MIN_SATURATION:
        return "guaranteed"
    lo, hi, red = SALARY_RED_FAMILY
    if hue >= lo or hue < hi:
        return red
    for lo, hi, family in SALARY_HUE_FAMILIES:
        if lo <= hue < hi:
            if family == "pre_arb":
                return nearest_legend_colour(argb, PRE_ARB_SHADES, threshold=441)
            return family
    return "unknown"


def clean_str(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def to_money(value):
    """
    '$3,009,259' / 3009259.0 / '-$1,700,000' -> number, else None.

    Whole-dollar amounts come back as int. The sheet does carry fractional
    dollars for some arbitration figures (e.g. 2474616.375), and those are
    kept as floats rather than rounded away.
    """
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        s = str(value).strip().replace(",", "").replace("$", "")
        if not s or not MONEY_RE.match(s):
            return None
        number = float(s)
    number = round(number, 4)
    return int(number) if number.is_integer() else number


def to_int(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    try:
        return int(float(s))
    except ValueError:
        return None


def to_mlb_id(value):
    i = to_int(value)
    # Current MLBAM ids are six digits (a few historic ones are five);
    # anything smaller is a scoresheet id, anything larger a stray salary
    # that slid into the wrong column.
    if i is not None and 10000 <= i <= 9999999:
        return i
    return None


def parse_service_time(value):
    """
    MLS cell -> ({"raw": "5.058", "years": 5, "days": 58}, eligible_year).

    For MLB players the cell is y.ddd. For AA/A prospects it's a 4-digit year
    (the year they become recall-eligible). Returns (service, year) with the
    unused one None.
    """
    if value is None or value == "":
        return None, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer() and 1900 <= int(value) <= 2200:
            return None, int(value)
        raw = f"{value:.3f}"
    else:
        raw = str(value).strip()
        if re.fullmatch(r"\d{4}", raw):
            return None, int(raw)
        try:
            raw = f"{float(raw):.3f}"
        except ValueError:
            return {"raw": raw, "years": None, "days": None}, None
    years, _, days = raw.partition(".")
    return {"raw": raw, "years": int(years), "days": int(days)}, None


def split_name(raw):
    """'Witt Jr., Bobby' -> ('Bobby', 'Witt Jr.')"""
    if raw is None:
        return None, None
    last, _, first = raw.partition(",")
    return first.strip() or None, last.strip() or None


def to_date_string(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.date().isoformat() if isinstance(value, datetime.datetime) else value.isoformat()
    return clean_str(value)


# ---------------------------------------------------------------------------
# team tab parsing


def find_header_row(ws):
    """Return (0-indexed row number, [salary years]) of the POS/MLB/MLS header."""
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=15)):
        if clean_str(row[COL_POS].value) == "POS" and clean_str(row[COL_ORG].value) == "MLB":
            years = [to_int(c.value) for c in row[COL_SALARY_START:COL_SALARY_END]]
            return idx, years
    raise ValueError(f"{ws.title}: could not find the POS/MLB/MLS header row")


def parse_team_header(ws):
    """Team name, division, GMs and the cap/cash summary at the top of a tab."""
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=1, max_row=6)]

    def cell(r, c):
        try:
            return rows[r][c]
        except IndexError:
            return None

    league_div = clean_str(cell(0, 4)) or ""
    league, _, division = league_div.partition("\n")
    founded = None
    m = re.search(r"f\.\s*(\d{4})", str(cell(0, 10) or ""))
    if m:
        founded = int(m.group(1))

    staff = []
    for r in range(2, 6):
        v = clean_str(cell(r, 14))
        if v and ":" in v:
            title, _, rest = v.partition(":")
            m = re.match(r"\s*(.*?)\s*(?:\(([^)]*)\))?\s*$", rest)
            staff.append(
                {
                    "title": title.strip(),
                    "name": (m.group(1) if m else rest).strip(),
                    "email": (m.group(2).strip() if m and m.group(2) else None),
                }
            )

    # Rows 4/5 (1-indexed) are the current/next season payroll lines:
    # year | PAYROLL | CAP | CASH | LUXTAX | 85-MAN | 40-MAN  then 30-MAN below.
    seasons = {}
    for r in (3, 4):
        year = to_int(cell(r, 4))
        if year:
            seasons[str(year)] = {
                "payroll": to_money(cell(r, 6)),
                "cap_space": to_money(cell(r, 9)),
                "cash": to_money(cell(r, 10)),
                "luxury_tax_space": to_money(cell(r, 11)),
            }
    roster_counts = {
        "85_man": to_int(cell(3, 12)),
        "40_man": to_int(cell(3, 13)),
        "30_man": to_int(cell(4, 13)),
    }

    return {
        "name": clean_str(cell(0, 0)),
        "league": clean_str(league),
        "division": clean_str(division),
        "founded": founded,
        "staff": staff,
        "seasons": seasons,
        "roster_counts": roster_counts,
        "titles": clean_str(cell(0, 11)),
    }


def parse_player_row(row, years, context, warnings, tab):
    """One player row -> dict, or None if the row doesn't look like a player."""
    name = clean_str(row[COL_NAME].value)
    mlb_id = to_mlb_id(row[COL_MLB_ID].value)
    if not name or not NAME_RE.match(name):
        return None
    if mlb_id is None:
        if clean_str(row[COL_POS].value):
            warnings.append(
                f"{tab}: row {row[0].row} '{name}' has no usable MLB id "
                f"(got {row[COL_MLB_ID].value!r}); skipped"
            )
        return None

    first, last = split_name(name)
    service_time, eligible_year = parse_service_time(row[COL_MLS].value)

    salaries = []
    for offset, year in enumerate(years):
        if year is None:
            continue
        cell = row[COL_SALARY_START + offset]
        # In the TRIPLE-A block the 2030 column doubles as RECALL DATE.
        if (
            context["level"] == "AAA"
            and COL_SALARY_START + offset == COL_RECALL_DATE
            and to_money(cell.value) is None
        ):
            continue
        amount = to_money(cell.value)
        if amount is None:
            continue
        fill = cell_fill(cell)
        salary_type = salary_type_for_fill(fill)
        if salary_type == "unknown":
            warnings.append(f"{tab}: {name} {year} salary has unrecognised fill {fill}")
        salaries.append(
            {
                "year": year,
                "amount": amount,
                "type": salary_type,
                "covered": bool(cell.font.italic),
                "fill": fill,
            }
        )

    recall_date = None
    if context["level"] == "AAA":
        v = row[COL_RECALL_DATE].value
        if to_money(v) is None:
            recall_date = to_date_string(v)

    notes = [clean_str(c.value) for c in row[COL_TERMS:]]
    notes = [n for n in notes if n]

    # Row-level highlights live on the non-salary cells (name, MLS, the
    # recall-date cell in the TRIPLE-A block ...).
    flag_cells = list(row[:COL_SALARY_START])
    if recall_date is not None:
        flag_cells.append(row[COL_RECALL_DATE])
    row_flags = set()
    for c in flag_cells:
        meaning = nearest_legend_colour(cell_fill(c), ROW_FILL_LEGEND)
        if meaning:
            row_flags.add(meaning)

    flag = row[COL_FLAG].value
    flag = str(to_int(flag)) if to_int(flag) is not None else clean_str(flag)
    return {
        "mlb_id": mlb_id,
        "name": name,
        "first_name": first,
        "last_name": last,
        "scoresheet_id": to_int(row[COL_SS_ID].value),
        "position": clean_str(row[COL_POS].value),
        "mlb_org": clean_str(row[COL_ORG].value),
        "level": context["level"],
        "roster_section": context["section"],
        "roster_subsection": context["subsection"],
        "position_group": context["group"],
        "on_40_man": flag == "1",
        "roster_flag": flag,
        "service_time": service_time,
        "eligible_year": eligible_year,
        "options": to_int(row[COL_OPT].value),
        "status": clean_str(row[COL_STA].value),
        "salaries": salaries,
        "buyout": to_money(row[COL_BUYOUT].value),
        "contract_terms": notes[0] if notes else None,
        "notes": notes[1:],
        "recall_date": recall_date,
        "signed_as_offseason_fa": bool(row[COL_NAME].font.italic),
        "flags": sorted(row_flags),
    }


def parse_financials(rows, years):
    """
    Best-effort capture of the FINANCIALS block under the roster.

    ``rows`` are the raw value lists from the FINANCIALS header onward. The
    block is free-form, so this keeps three things: year-keyed summary lines
    (salary cap, payroll, cap space, cash reserves ...), the ledger of
    liabilities/credits (released players, salary carried by other teams),
    and the cash income/expenditure ledger.
    """
    summary = {}
    liabilities = []
    cash_ledger = []
    ifa = {"trades": []}
    section = None

    for row in rows:
        label = clean_str(row[1]) if len(row) > 1 else None
        # The IFA "Base:" line has nothing in the label column.
        if section == "ifa" and len(row) > 4 and clean_str(row[4]) == "Base:":
            ifa["base"] = to_money(row[6] if len(row) > 6 else None)
            ifa["can_acquire"] = to_money(row[10] if len(row) > 10 else None)
            ifa["total"] = to_money(row[12] if len(row) > 12 else None)
            continue
        if not label:
            continue
        upper = label.upper()
        if upper in ("$ RESERVES LIABILITIES", "PAYROLL INCOME + EXPENDITURES"):
            section = "liabilities"
            continue
        if upper == "CASH INCOME + EXPENDITURES":
            section = "cash"
            continue
        if upper == "IFA CAP SPACE":
            section = "ifa"
            continue
        if upper == "DRAFT PICK TRADES":
            section = "draft_picks"
            continue
        if upper in ("FINANCIALS", "TOTAL FINANCIALS"):
            continue

        amounts = {
            str(year): to_money(row[COL_SALARY_START + i])
            for i, year in enumerate(years)
            if year and len(row) > COL_SALARY_START + i and to_money(row[COL_SALARY_START + i]) is not None
        }
        desc = clean_str(row[4]) if len(row) > 4 else None
        first_amount = amounts.get(str(years[0])) if years else None

        if section == "ifa":
            if upper != "DATE" and first_amount is not None:
                ifa["trades"].append({"date": to_date_string(row[1]), "teams": desc, "amount": first_amount})
            continue

        if section == "liabilities" and first_amount is not None:
            liabilities.append({"player": label, "description": desc, "amount": first_amount})
            continue

        if section == "cash" and (amounts or desc):
            entry = {"label": label, "description": desc}
            if len(amounts) > 1:
                entry["amounts"] = amounts
            else:
                entry["amount"] = first_amount
            cash_ledger.append(entry)
            continue

        if section is None and amounts:
            summary[label] = amounts

    return {"summary": summary, "liabilities": liabilities, "cash_ledger": cash_ledger, "ifa": ifa}


def parse_team_tab(ws, warnings):
    """Parse one team worksheet into {"team": ..., "players": [...], "financials": ...}."""
    header_idx, years = find_header_row(ws)
    team = parse_team_header(ws)
    tab = ws.title

    players = []
    context = {"level": "MLB", "section": "ACTIVE ROSTER", "subsection": None, "group": None}
    financial_rows = []
    in_financials = False
    minors_names = {}

    for row in ws.iter_rows(min_row=header_idx + 2):
        if in_financials:
            financial_rows.append([c.value for c in row])
            continue

        label = clean_str(row[COL_NAME].value)
        has_id = to_mlb_id(row[COL_MLB_ID].value) is not None
        if label and label.upper() == FINANCIALS_HEADER and not has_id:
            in_financials = True
            continue

        # Section headers live in the name column with no MLB id. (The
        # position-group headers carry "SS#"/"MLB#" column labels, which is
        # why this checks for a usable id rather than an empty cell.)
        if label and not has_id and not NAME_RE.match(label):
            matched = False
            for pattern, level, section in LEVEL_SECTIONS:
                if pattern.match(label):
                    context = {"level": level, "section": section, "subsection": None, "group": None}
                    if level in ("AAA", "AA", "A"):
                        # "TRIPLE-A UNIVERSAL BASEBALL ASSOCIATION" -> affiliate name
                        affiliate = re.sub(r"^(TRIPLE|DOUBLE|SINGLE)[- ]A\b\s*:?\s*", "", label, flags=re.I).strip()
                        minors_names[level] = affiliate or None
                    matched = True
                    break
            if not matched:
                if label.upper() in AAA_SUBSECTIONS:
                    context = dict(context, subsection=AAA_SUBSECTIONS[label.upper()])
                elif label.upper() in POSITION_GROUPS:
                    context = dict(context, group=label.upper())
            continue

        player = parse_player_row(row, years, context, warnings, tab)
        if player:
            players.append(player)

    team["affiliates"] = {"AAA": minors_names.get("AAA"), "AA": minors_names.get("AA"), "A": minors_names.get("A")}

    seen = {}
    for p in players:
        if p["mlb_id"] in seen:
            warnings.append(f"{tab}: MLB id {p['mlb_id']} appears twice ({seen[p['mlb_id']]} / {p['name']})")
        seen[p["mlb_id"]] = p["name"]

    return {
        "tab": tab,
        "team": team,
        "salary_years": [y for y in years if y],
        "players": players,
        "financials": parse_financials(financial_rows, [y for y in years if y]),
    }


# ---------------------------------------------------------------------------
# workbook entry points


def is_team_tab(title):
    return title not in NON_TEAM_TABS and not NON_TEAM_TAB_RE.match(title)


def fetch_workbook(sheet_id, timeout=120):
    """Download the sheet's xlsx export and return the raw bytes."""
    resp = requests.get(EXPORT_URL.format(sheet_id=sheet_id), timeout=timeout)
    resp.raise_for_status()
    return resp.content


def team_tab_number(title):
    """'Bulldog #18' -> 18. Team tabs carry the team number after a '#'."""
    m = re.search(r"#\s*(\d+)\s*$", title or "")
    return int(m.group(1)) if m else None


def load_workbook(source):
    """``source`` is a path, a file-like object, or raw bytes."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    return openpyxl.load_workbook(source, data_only=True)


def parse_workbook(source, tabs=None):
    """
    Parse every team tab in the roster workbook.

    Returns {"generated": iso timestamp, "teams": [...], "warnings": [...]}.
    Players are nested under their team; ``mlb_id`` is unique within a team
    and is the key to join against elsewhere. Cross-team duplicates (a player
    listed on two tabs) are reported in ``warnings`` rather than dropped.
    """
    wb = load_workbook(source)
    warnings = []
    teams = []
    for title in wb.sheetnames:
        if not is_team_tab(title):
            continue
        if tabs and title not in tabs:
            continue
        teams.append(parse_team_tab(wb[title], warnings))

    owners = {}
    for t in teams:
        for p in t["players"]:
            owners.setdefault(p["mlb_id"], []).append((t["tab"], p["name"]))
    for mlb_id, where in owners.items():
        if len(where) > 1:
            listing = ", ".join(f"{tab}:{name}" for tab, name in where)
            warnings.append(f"MLB id {mlb_id} listed on multiple teams: {listing}")

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "teams": teams,
        "warnings": warnings,
    }


def flatten_players(parsed):
    """Convenience: one flat list of players with ``npl_team`` added."""
    out = []
    for t in parsed["teams"]:
        for p in t["players"]:
            out.append(dict(p, npl_team=t["team"]["name"], npl_tab=t["tab"]))
    return out
