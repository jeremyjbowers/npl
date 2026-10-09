"""Pure parsers for the NPL roster workbook and the Team Owners tab.

Players are identified only by the MLB ID in column D. A missing ID is
reported and skipped. Name search is not a fallback.
"""

import re


TEAM_TAB_RE = re.compile(r"^(?P<name>.+?)\s+#(?P<number>\d+)\s*$")
MANAGER_RE = re.compile(
    r"(?P<title>[A-Za-z][^:()]{1,80}?)\s*:\s*(?P<name>[^:()]{1,80}?)\s*\((?P<email>[^)\s]+@[^)\s]+)\)"
)
YEAR_RE = re.compile(r"^\d{4}$")
MLB_ID_RE = re.compile(r"^\d{5,9}$")

GROUP_LABELS = {
    "STARTING PITCHERS",
    "RELIEF PITCHERS",
    "INFIELDERS",
    "OUTFIELDERS",
    "CATCHERS",
    "PITCHERS",
    "HITTERS",
    "POSITION PLAYERS",
    "DESIGNATED HITTERS",
    "UTILITY",
}

ROSTER_SECTIONS = (
    ("ACTIVE ROSTER", "active"),
    ("7-DAY", "il7"),
    ("56-DAY", "il56"),
    ("END OF SEASON", "eos"),
    ("RESTRICTED", "restricted"),
    ("ON OPTION", "option"),
    ("ASSIGNED OUTRIGHT", "outright"),
    ("NON-ROSTER", "nonroster"),
    ("FOREIGN", "foreign"),
    ("RETIRED", "retired"),
)

FARM_SECTIONS = (
    ("TRIPLE-A", "aaa", "triple_a"),
    ("DOUBLE-A", "aa", "double_a"),
    ("SINGLE-A", "a", "single_a"),
)

SECTION_FLAGS = {
    "active": {"roster_30man": True, "roster_85man": True},
    "il7": {"roster_7dayIL": True, "roster_85man": True},
    "il56": {"roster_56dayIL": True, "roster_85man": True},
    "eos": {"roster_eosIL": True, "roster_85man": True},
    "restricted": {"roster_restricted": True, "roster_85man": True},
    "option": {"roster_tripleA_option": True, "roster_tripleA": True, "roster_85man": True},
    "aaa": {"roster_tripleA": True, "roster_85man": True},
    "outright": {"roster_outrighted": True, "roster_85man": True},
    "nonroster": {"roster_nonroster": True, "roster_85man": True},
    "foreign": {"roster_foreign": True},
    "retired": {"roster_retired": True},
    "aa": {"roster_doubleA": True, "roster_85man": True},
    "a": {"roster_singleA": True, "roster_85man": True},
}


def cell(row, index):
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def pretty(text):
    text = " ".join(str(text or "").split())
    if text.isupper():
        return text.title()
    return text


def short_name_from_tab(title):
    match = TEAM_TAB_RE.match((title or "").strip())
    if not match:
        return ""
    return match.group("name").strip()


def parse_dollars(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    cleaned = (
        text.replace("$", "")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "")
        .strip()
    )
    if not cleaned or not cleaned[0].isdigit():
        return None
    if "." in cleaned:
        cleaned = cleaned.split(".", 1)[0]
    if not cleaned.isdigit():
        return None
    amount = int(cleaned)
    return -amount if negative else amount


def parse_owners_sheet(rows):
    """Return people from the Team Owners tab.

    A blank team cell continues the team from the row above. Co-owners are
    listed that way.
    """
    header_at = None
    for index, row in enumerate(rows):
        labels = [cell(row, i).lower() for i in range(min(len(row), 4))]
        if "team" in labels and "name" in labels and "email" in labels:
            header_at = index
            break
    if header_at is None:
        return []

    people = []
    current_team = ""
    for row in rows[header_at + 1 :]:
        team_cell = cell(row, 0)
        name = cell(row, 1)
        year_text = cell(row, 2)
        email = cell(row, 3).lower()
        if team_cell:
            current_team = team_cell
        if not name and not email:
            continue
        year_joined = int(year_text) if year_text.isdigit() else None
        people.append(
            {
                "team_label": current_team,
                "name": name,
                "year_joined": year_joined,
                "email": email,
                "twitter": cell(row, 4),
                "phone": cell(row, 5),
                "hometown": cell(row, 6),
                "bio": cell(row, 7),
                "title": "",
            }
        )
    return people


def _header_map(row):
    found = {}
    for index, raw in enumerate(row):
        label = cell(row, index).upper()
        if label:
            found[label] = index
    return found


def _empty_ledger(year):
    return {
        "year": year,
        "payroll": None,
        "cap_space": None,
        "cash": None,
        "luxury_tax": None,
        "luxury_note": "",
        "salary_cap": None,
        "available_cap": None,
        "cash_reserves": None,
        "roster_85": None,
        "roster_40": None,
        "roster_30": None,
        "ifa_base": None,
        "ifa_acquired": None,
        "ifa_total": None,
    }


def _parse_league_division(text):
    flat = " ".join(str(text or "").replace("\n", " ").split())
    upper = flat.upper()
    league = None
    if "AMERICAN" in upper:
        league = "AL"
    elif "NATIONAL" in upper:
        league = "NL"
    division = re.sub(r"AMERICAN LEAGUE|NATIONAL LEAGUE", "", upper)
    division = re.sub(r"\bDIVISION\b", "", division).strip()
    return league, pretty(division) if division else ""


def _classify_section(label):
    upper = " ".join(label.upper().split())
    if not upper:
        return None, ""
    if upper in GROUP_LABELS or upper.startswith("STARTING PITCH") or upper.startswith("RELIEF PITCH"):
        return "group", ""
    if upper == "FINANCIALS" or upper.startswith("FINANCIAL"):
        return "financials", ""
    for prefix, key in ROSTER_SECTIONS:
        if upper.startswith(prefix):
            return key, label
    for prefix, key, _farm in FARM_SECTIONS:
        if upper.startswith(prefix):
            rest = label[len(prefix) :].strip(" -")
            return key, rest
    return None, ""


def _split_player_name(raw):
    raw = raw.strip()
    if "," in raw:
        last, first = raw.split(",", 1)
        return first.strip(), last.strip()
    parts = raw.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return raw, ""


def _flags(section, on_40):
    flags = {
        "roster_85man": section not in {"foreign", "retired"},
        "roster_40man": on_40,
        "roster_30man": False,
        "roster_7dayIL": False,
        "roster_56dayIL": False,
        "roster_eosIL": False,
        "roster_restricted": False,
        "roster_tripleA": False,
        "roster_tripleA_option": False,
        "roster_outrighted": False,
        "roster_foreign": False,
        "roster_retired": False,
        "roster_nonroster": False,
        "roster_doubleA": False,
        "roster_singleA": False,
    }
    flags.update(SECTION_FLAGS.get(section or "", {}))
    if on_40:
        flags["roster_40man"] = True
    return flags


def _service_fields(mls_cell, opt_cell, sta_cell):
    mls_cell = (mls_cell or "").strip()
    payload = {"mls_time": "", "mls_year": "", "options": None, "sta": (sta_cell or "").strip()}
    if "." in mls_cell:
        payload["mls_time"] = mls_cell
    elif YEAR_RE.match(mls_cell):
        payload["mls_year"] = mls_cell
    opt = (opt_cell or "").strip()
    if opt.isdigit():
        payload["options"] = int(opt)
    return payload


def _contract_from_row(row, salary_years, buyout_col, terms_col):
    years = []
    notes = []
    for year, index in sorted(salary_years.items()):
        raw = cell(row, index)
        if not raw:
            continue
        amount = parse_dollars(raw)
        if amount is None:
            notes.append(f"{year}: {raw}")
        else:
            years.append({"year": year, "amount": amount})
    buyout_raw = cell(row, buyout_col) if buyout_col is not None else ""
    buyout_amount = parse_dollars(buyout_raw)
    if terms_col is not None:
        for index in range(terms_col, len(row)):
            extra = cell(row, index)
            if extra:
                notes.append(extra)
    if not years and buyout_amount is None and not notes:
        return None
    return {
        "years": years,
        "buyout": buyout_raw if buyout_amount is not None else "",
        "buyout_amount": buyout_amount,
        "notes": "; ".join(notes),
    }


def _apply_year_amounts(ledger, row, salary_years, field):
    for year, index in salary_years.items():
        raw = cell(row, index)
        if raw == "":
            continue
        amount = parse_dollars(raw)
        if amount is None:
            continue
        entry = ledger.setdefault(year, _empty_ledger(year))
        entry[field] = amount


def _next_amount(row, start):
    for index in range(start + 1, min(len(row), start + 6)):
        amount = parse_dollars(cell(row, index))
        if amount is not None:
            return amount
    return None


def _line_kind(section, label, detail):
    blob = f"{label} {detail}".lower()
    if "carried" in blob and "reserve" not in blob:
        return "carried_salary"
    if section == "draft_pick":
        return "draft_pick"
    if "termination" in blob:
        return "termination_pay"
    if "cap overage" in blob:
        return "cap_overage"
    if label.lower().startswith("trade") or ">" in detail or blob.startswith("r5"):
        return "trade"
    if "draft slot" in blob:
        return "draft_slot"
    if "draft bonus" in blob:
        return "draft_bonus"
    if "ifa" in blob:
        return "ifa"
    if "npl distributed" in blob:
        return "distribution"
    if "playoff" in blob:
        return "playoff"
    if "penalt" in blob:
        return "penalty"
    if "cash reserve" in blob or "carried $" in blob:
        return "cash_reserves"
    return "other"


def _counterparty(detail):
    match = re.search(r"\bby\s+(.+)$", detail, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if ">" in detail:
        return detail.strip()
    return ""


def _snapshot_row(row, columns):
    payroll_at = columns.get("PAYROLL")
    if payroll_at is None:
        return None
    year = None
    for index in range(payroll_at):
        if YEAR_RE.match(cell(row, index)):
            year = int(cell(row, index))
            break
    if year is None:
        return None
    entry = _empty_ledger(year)
    cap_at = columns.get("CAP")
    cash_at = columns.get("CASH")
    lux_at = columns.get("LUXTAX")
    man_85 = columns.get("85-MAN")
    man_40 = columns.get("40-MAN")
    entry["payroll"] = parse_dollars(cell(row, payroll_at))
    entry["cap_space"] = parse_dollars(cell(row, cap_at))
    entry["available_cap"] = entry["cap_space"]
    entry["cash"] = parse_dollars(cell(row, cash_at))
    lux_raw = cell(row, lux_at)
    lux_amount = parse_dollars(lux_raw)
    if lux_amount is None and lux_raw:
        entry["luxury_note"] = lux_raw
    else:
        entry["luxury_tax"] = lux_amount
    if man_85 is not None and cell(row, man_85).isdigit():
        entry["roster_85"] = int(cell(row, man_85))
    if man_40 is not None and cell(row, man_40).isdigit():
        entry["roster_40"] = int(cell(row, man_40))
    if entry["payroll"] is None and entry["cap_space"] is None and entry["cash"] is None:
        return None
    for index, raw in enumerate(row):
        if cell(row, index).upper() == "30-MAN":
            nxt = cell(row, index + 1)
            if nxt.isdigit():
                entry["roster_30"] = int(nxt)
    return entry


def _parse_managers(rows):
    """Staff lines in the header: GM, AGM, POBO, co-owner, and similar."""
    managers = []
    seen = set()
    for row in rows[:25]:
        if cell(row, 1).upper() in {"ACTIVE ROSTER", "FINANCIALS"}:
            break
        for raw in row:
            text = " ".join(str(raw).split())
            for match in MANAGER_RE.finditer(text):
                email = match.group("email").strip().lower()
                if email in seen:
                    continue
                seen.add(email)
                managers.append(
                    {
                        "title": " ".join(match.group("title").split()),
                        "name": match.group("name").strip(),
                        "email": email,
                    }
                )
    return managers


def _financial_lines(rows, salary_years, ledger):
    lines = []
    section = ""
    saw_payroll = False
    sort_order = 0
    started = False
    for row in rows:
        label = cell(row, 1)
        upper = " ".join(label.upper().split())
        if upper == "FINANCIALS":
            started = True
            section = "summary"
            continue
        if not started:
            continue
        if upper.startswith("SALARY CAP"):
            _apply_year_amounts(ledger, row, salary_years, "salary_cap")
            continue
        if upper.startswith("TOTAL MAJOR LEAGUE PAYROLL"):
            _apply_year_amounts(ledger, row, salary_years, "payroll")
            continue
        if "CAP SPACE" in upper:
            _apply_year_amounts(ledger, row, salary_years, "available_cap")
            continue
        if upper.startswith("CASH RESERVES"):
            _apply_year_amounts(ledger, row, salary_years, "cash_reserves")
            continue
        if upper.startswith("IFA"):
            section = "ifa"
            continue
        if upper.startswith("DRAFT PICK"):
            section = "draft_pick"
            continue
        if upper.startswith("PAYROLL INCOME"):
            section = "payroll"
            saw_payroll = True
            continue
        if upper.startswith("CASH INCOME"):
            section = "cash"
            continue
        if upper.startswith("$ RESERVES") or upper in {"TOTAL FINANCIALS", "DATE"}:
            continue
        joined = " ".join(cell(row, i) for i in range(len(row))).upper()
        if "BASE:" in joined and ("TOTAL" in joined or "CAN ACQUIRE" in joined):
            target_year = min(ledger) if ledger else None
            if target_year is not None:
                entry = ledger[target_year]
                for index, raw in enumerate(row):
                    token = cell(row, index).upper()
                    if token.startswith("BASE"):
                        entry["ifa_base"] = _next_amount(row, index)
                    elif token.startswith("CAN ACQUIRE"):
                        entry["ifa_acquired"] = _next_amount(row, index)
                    elif token.startswith("TOTAL"):
                        entry["ifa_total"] = _next_amount(row, index)
            continue
        if section not in {"payroll", "cash", "ifa", "draft_pick"}:
            continue
        detail = cell(row, 4)
        if not label and not detail:
            continue
        emitted = False
        for year, index in sorted(salary_years.items()):
            raw = cell(row, index)
            if not raw:
                continue
            amount = parse_dollars(raw)
            text_value = "" if amount is not None else raw
            player_name = label if "," in label else ""
            lines.append(
                {
                    "section": section,
                    "kind": _line_kind(section, label, detail),
                    "label": label,
                    "counterparty": _counterparty(detail),
                    "player_name": player_name,
                    "year": year,
                    "amount": amount,
                    "text_value": text_value,
                    "note": detail,
                    "sort_order": sort_order,
                }
            )
            emitted = True
        if emitted:
            sort_order += 1
    return lines, saw_payroll


def parse_team_sheet(rows):
    """Turn one team tab into players, contracts, ledger years, and cash lines."""
    rows = [list(row) for row in rows]
    full_name = pretty(cell(rows[0], 0)) if rows else ""
    league, division = _parse_league_division(cell(rows[0], 4) if rows else "")
    founded = None
    for raw in rows[0] if rows else []:
        match = re.search(r"f\.\s*(\d{4})", str(raw))
        if match:
            founded = int(match.group(1))
            break

    columns = {}
    for row in rows[:12]:
        labels = _header_map(row)
        if "PAYROLL" in labels and "CAP" in labels and "CASH" in labels:
            columns = labels
            break

    salary_years = {}
    buyout_col = None
    terms_col = None
    for row in rows[:25]:
        if not any(cell(row, index).upper() == "POS" for index in range(len(row))):
            continue
        for index in range(len(row)):
            token = cell(row, index)
            if YEAR_RE.match(token):
                salary_years[int(token)] = index
            elif token.upper() == "BUYOUT":
                buyout_col = index
            elif "CONTRACT" in token.upper():
                terms_col = index
        break

    ledger = {}
    if columns:
        for row in rows[:12]:
            if any(cell(row, index).upper() == "POS" for index in range(len(row))):
                break
            snapshot = _snapshot_row(row, columns)
            if snapshot:
                ledger[snapshot["year"]] = snapshot

    players = []
    unresolved = []
    farms = {"triple_a": "", "double_a": "", "single_a": ""}
    section = None
    section_label = ""
    seen_ids = set()
    in_financials = False
    for row in rows:
        label = cell(row, 1)
        kind, extra = _classify_section(label)
        mlb_id = cell(row, 3)
        mlb_id = mlb_id if MLB_ID_RE.match(mlb_id) else ""
        if kind == "financials":
            in_financials = True
            continue
        if in_financials:
            continue
        if mlb_id and label:
            if mlb_id in seen_ids:
                unresolved.append(
                    {"raw_name": label, "mlb_id": mlb_id, "reason": "duplicate MLB ID on this sheet"}
                )
                continue
            seen_ids.add(mlb_id)
            first_name, last_name = _split_player_name(label)
            service = _service_fields(cell(row, 6), cell(row, 7), cell(row, 8))
            on_40 = cell(row, 0) == "1"
            scoresheet = cell(row, 2)
            players.append(
                {
                    "mlb_id": mlb_id,
                    "scoresheet_id": scoresheet if scoresheet.isdigit() else "",
                    "raw_name": label,
                    "first_name": first_name,
                    "last_name": last_name,
                    "position": cell(row, 4),
                    "mlb_org": cell(row, 5),
                    "section": section or "",
                    "section_label": section_label,
                    "on_40": on_40,
                    "flags": _flags(section, on_40),
                    "contract": _contract_from_row(row, salary_years, buyout_col, terms_col),
                    **service,
                }
            )
            continue
        if kind == "group":
            continue
        if kind in {"aaa", "aa", "a"}:
            section = kind
            section_label = label
            farm_field = {"aaa": "triple_a", "aa": "double_a", "a": "single_a"}[kind]
            if extra:
                farms[farm_field] = pretty(extra)
            continue
        if kind:
            section = kind
            section_label = label
            continue
        if "," in label and cell(row, 0) in {"", "-", "1"}:
            unresolved.append(
                {
                    "raw_name": label,
                    "mlb_id": cell(row, 3),
                    "reason": "row has no MLB ID",
                }
            )

    lines, saw_payroll = _financial_lines(rows, salary_years, ledger)
    return {
        "full_name": full_name,
        "league": league,
        "division": division,
        "founded": founded,
        "farms": farms,
        "salary_years": sorted(salary_years),
        "ledger": [ledger[year] for year in sorted(ledger)],
        "players": players,
        "lines": lines,
        "unresolved": unresolved,
        "managers": _parse_managers(rows),
        "saw_payroll_section": saw_payroll,
    }
