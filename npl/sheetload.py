"""Read the roster workbook the way the league keeps its books.

Team tabs color each salary cell from the Key legend. White is a guaranteed
salary. Yellow, red, and purple are club, vesting, and player options.
The green and blue fills are the pre-arbitration bands and arbitration.
The FINANCIALS block under the roster is the cap, the cash reserves, and
every carried-salary, bonus, and penalty line.
"""

import datetime
import re


GUARANTEED = "guaranteed"
CLUB_OPTION = "club_option"
VESTING_OPTION = "vesting_option"
PLAYER_OPTION = "player_option"
PRE_ARB_0 = "pre_arb_0"
PRE_ARB_1 = "pre_arb_1"
PRE_ARB_2 = "pre_arb_2"
ARBITRATION = "arbitration"
RECALL_HOLD = "recall_hold"
PENDING_FA = "pending_fa"
PENDING_TERMS = "pending_terms"

OPTION_CLASSES = (CLUB_OPTION, VESTING_OPTION, PLAYER_OPTION)

# Team-roster markers. The workbook key is yellow, red, and purple for the
# three option kinds. Guaranteed, pre-arbitration, and arbitration stay plain.
OPTION_CELL_CLASS = {
    CLUB_OPTION: "salary-club_option",
    VESTING_OPTION: "salary-vesting_option",
    PLAYER_OPTION: "salary-player_option",
}
BUYOUT_CELL_CLASS = "salary-buyout"


def salary_cell_class(name):
    """CSS class for a contract year. Only option years are marked."""
    return OPTION_CELL_CLASS.get(name or "", "")


def contract_has_buyout(contract):
    """A buyout is the contract's buyout amount, not a year cell."""
    if not contract:
        return False
    if isinstance(contract, dict):
        amount = contract.get("buyout_amount")
    else:
        amount = getattr(contract, "buyout_amount", None)
    return bool(amount)


def buyout_cell_class(contract):
    if contract_has_buyout(contract):
        return BUYOUT_CELL_CLASS
    return ""

# Key tab swatches, sampled from the live roster workbook.
SALARY_COLORS = (
    ((255, 255, 0), CLUB_OPTION),
    ((255, 0, 0), VESTING_OPTION),
    ((180, 167, 214), PLAYER_OPTION),
    ((217, 234, 211), PRE_ARB_0),
    ((182, 215, 168), PRE_ARB_1),
    ((147, 196, 125), PRE_ARB_2),
    ((164, 194, 244), ARBITRATION),
    ((244, 199, 195), RECALL_HOLD),
    ((153, 0, 255), PENDING_FA),
    ((183, 183, 183), PENDING_TERMS),
)

# MLB CBA minimums the rules adopt through the current agreement.
# 2028 and after wait on the next CBA.
LEAGUE_MINIMUMS = {
    2023: 700_000,
    2024: 720_000,
    2025: 740_000,
    2026: 760_000,
    2027: 780_000,
}

# International bonus pool the league wires into cash reserves each year.
IFA_ALLOTMENT = {
    "bottom": 5_750_000,
    "middle": 5_250_000,
    "top": 4_750_000,
}

PROJECTION_LABELS = {
    "SALARY CAP": "salary_cap",
    "TOTAL MAJOR LEAGUE PAYROLL": "payroll",
    "TOTAL AVAILABLE MAJOR LEAGUE CAP SPACE": "cap_space",
    "CASH RESERVES": "cash",
}

SUMMARY_LABELS = ("PAYROLL", "CAP", "CASH", "LUXTAX", "85-MAN", "40-MAN", "30-MAN")


class Cell:
    def __init__(self, value="", bg=None, italic=False):
        self.value = "" if value is None else str(value)
        self.bg = bg
        self.italic = bool(italic)

    def __repr__(self):
        return f"Cell({self.value!r})"


def as_cell(value):
    if isinstance(value, Cell):
        return value
    return Cell(value)


def normalize(grid):
    return [[as_cell(cell) for cell in row] for row in (grid or [])]


def cell_text(cell):
    if cell is None:
        return ""
    if isinstance(cell, Cell):
        return cell.value or ""
    return str(cell)


def parse_money(value):
    """Dollars from a sheet cell. Blanks and words are None. Negatives stay negative."""
    if value is None:
        return None
    text = cell_text(value).strip()
    if not text or text in {"-", "—", "–"}:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    cleaned = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    cleaned = cleaned.replace("-", "").strip()
    if not cleaned or not cleaned[0].isdigit():
        return None
    if "." in cleaned:
        cleaned = cleaned.split(".", 1)[0]
    if not cleaned.isdigit():
        return None
    amount = int(cleaned)
    return -amount if negative else amount


def parse_date(value):
    text = cell_text(value).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def salary_class(bg):
    """Map a salary cell's background to the Key legend. Bare cells are guaranteed."""
    if not bg:
        return GUARANTEED
    if all(channel >= 250 for channel in bg[:3]):
        return GUARANTEED
    best_name = GUARANTEED
    best_distance = None
    for target, name in SALARY_COLORS:
        distance = sum((left - right) ** 2 for left, right in zip(bg[:3], target))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = name
    if best_distance is not None and best_distance <= 18 ** 2 * 3:
        return best_name
    return GUARANTEED


def league_minimum(year):
    return LEAGUE_MINIMUMS.get(year)


def cash_is_overdrawn(cash_before, cash_after):
    """A filing may not open a cash deficit or deepen one that already exists.

    Clubs already borrowing against payroll can still make moves that do not
    spend more cash. Luxury tax and cash sent out both count as spending.
    """
    return cash_after < 0 and cash_after < cash_before


def settle_books(cap_space, cash, cap_delta=0, cash_delta=0):
    """Apply a filing to cap space and cash.

    Payroll added past the cap is a luxury tax, paid 1:1 from cash reserves.
    Cutting payroll does not refund tax already paid. Cash is not allowed
    to finish negative: that is both a cash-reserve deficit and a luxury-tax
    limit (a club can only pass the cap by what it has in cash).
    """
    cap_after = (cap_space or 0) + cap_delta
    over_before = max(0, -(cap_space or 0))
    over_after = max(0, -cap_after)
    new_tax = max(0, over_after - over_before)
    cash_after = (cash or 0) + cash_delta - new_tax
    return {
        "cap_after": cap_after,
        "cash_after": cash_after,
        "luxury_tax": new_tax,
    }


def _texts(row):
    return [cell_text(cell).strip() for cell in row]


def _year_columns(header):
    found = []
    for index, text in enumerate(header):
        if text.isdigit() and len(text) == 4:
            found.append((int(text), index))
    return found


def _header_index(grid):
    for index, row in enumerate(grid[:20]):
        header = [text.upper() for text in _texts(row)]
        if "BUYOUT" in header and _year_columns(header):
            return index
    return None


def founded_year(grid):
    for row in grid[:6]:
        for text in _texts(row):
            match = re.search(r"f\.\s*(\d{4})", text, re.I)
            if match:
                return int(match.group(1))
    return None


def _summary(grid):
    labels = {}
    for row_index, row in enumerate(grid[:8]):
        for col_index, text in enumerate(_texts(row)):
            key = text.upper()
            if key in SUMMARY_LABELS and key not in labels:
                labels[key] = (row_index, col_index)
    seasons = []
    for row in grid[:8]:
        texts = _texts(row)
        year = None
        for text in texts[:6]:
            if text.isdigit() and len(text) == 4:
                year = int(text)
                break
        if year is None:
            continue
        entry = {"year": year}
        for label, key in (
            ("PAYROLL", "payroll"),
            ("CAP", "cap_space"),
            ("CASH", "cash"),
            ("LUXTAX", "luxury"),
            ("85-MAN", "roster_85"),
            ("40-MAN", "roster_40"),
            ("30-MAN", "roster_30"),
        ):
            entry[key] = _labeled_number(row, labels.get(label))
        seasons.append(entry)
    return seasons


def _labeled_number(row, label_pos):
    if not label_pos:
        return None
    _, col_index = label_pos
    if col_index >= len(row):
        return None
    amount = parse_money(row[col_index])
    if amount is not None:
        return amount
    if col_index + 1 < len(row):
        return parse_money(row[col_index + 1])
    return None


def _money_by_year(row, year_cols):
    found = []
    for year, index in year_cols:
        if index >= len(row):
            continue
        amount = parse_money(row[index])
        if amount is None:
            continue
        text = cell_text(row[index]).strip()
        if text.isdigit() and len(text) == 4:
            continue
        found.append((year, amount))
    return found


def _labeled_amounts(row):
    """Pair 'Base:' with the dollar cell that follows it, when amounts are not on year columns."""
    pairs = []
    pending = None
    for text in _texts(row):
        if not text:
            continue
        if "$" in text:
            amount = parse_money(text)
            if amount is not None and pending:
                pairs.append((pending.rstrip(":"), amount))
                pending = None
            continue
        if parse_money(text) is None:
            pending = text
    return pairs


def _detail_text(row, label):
    pieces = []
    for text in _texts(row):
        if not text or text == label:
            continue
        if parse_money(text) is not None and "$" in text:
            continue
        if text.isdigit() and len(text) == 4:
            continue
        pieces.append(text)
    return pieces[0] if pieces else ""


def _section_book(text):
    upper = text.upper()
    if "DRAFT PICK" in upper:
        return "draft"
    if upper.startswith("PAYROLL INCOME"):
        return "payroll"
    if upper.startswith("CASH INCOME"):
        return "cash"
    if "IFA" in upper and "EXPEND" not in upper and "BONUS" not in upper:
        return "ifa"
    return None


def _projection_key(text):
    upper = text.upper().strip()
    for label, key in PROJECTION_LABELS.items():
        if upper == label or upper.startswith(label):
            return key
    return None


def _financials(grid, year_cols, start):
    projections = {}
    lines = []
    book = None
    order = 0
    for row in grid[start + 1 :]:
        texts = [text for text in _texts(row) if text]
        if not texts:
            continue
        label = texts[0]
        switched = _section_book(label)
        if switched:
            book = switched
            continue
        if book == "draft":
            continue
        projection = _projection_key(label)
        amounts = _money_by_year(row, year_cols)
        if projection and amounts:
            for year, amount in amounts:
                bucket = projections.setdefault(year, {})
                bucket[projection] = amount
            continue
        pairs = _labeled_amounts(row)
        if len(pairs) >= 2 and year_cols:
            for label_bit, amount in pairs:
                lines.append(
                    {
                        "year": year_cols[0][0],
                        "book": book or "cash",
                        "label": label_bit,
                        "detail": "",
                        "amount": amount,
                        "row_order": order,
                    }
                )
                order += 1
            continue
        if not amounts:
            continue
        if book is None:
            book_name = "payroll" if "CARRIED" in label.upper() or "LIABIL" in label.upper() else "cash"
        else:
            book_name = book
        detail = _detail_text(row, label)
        for year, amount in amounts:
            lines.append(
                {
                    "year": year,
                    "book": book_name,
                    "label": label,
                    "detail": detail,
                    "amount": amount,
                    "row_order": order,
                }
            )
            order += 1
    return projections, lines


def parse_team_sheet(grid):
    """One team tab: summary books, colored salaries, and the financials ledger."""
    rows = normalize(grid)
    header_at = _header_index(rows)
    header = _texts(rows[header_at]) if header_at is not None else []
    year_cols = _year_columns(header)
    buyout_at = next((i for i, text in enumerate(header) if text.upper() == "BUYOUT"), None)
    terms_at = next((i for i, text in enumerate(header) if "CONTRACT TERM" in text.upper()), None)
    financials_at = None
    for index, row in enumerate(rows):
        if any(text.upper() == "FINANCIALS" for text in _texts(row)):
            financials_at = index
            break

    players = []
    stop = financials_at if financials_at is not None else len(rows)
    begin = (header_at + 1) if header_at is not None else 0
    for row in rows[begin:stop]:
        if not row:
            continue
        marker = cell_text(row[0]).strip() if row else ""
        if marker not in {"1", "-"}:
            continue
        name = cell_text(row[1]).strip() if len(row) > 1 else ""
        if not name or name.upper() in {"POS", "ACTIVE ROSTER"}:
            continue
        years = []
        pending = False
        for year, index in year_cols:
            if index >= len(row):
                continue
            amount = parse_money(row[index])
            if amount is None:
                continue
            pending = pending or row[index].italic
            years.append(
                {
                    "year": year,
                    "amount": amount,
                    "salary_class": salary_class(row[index].bg),
                    "italic": row[index].italic,
                }
            )
        buyout = None
        if buyout_at is not None and buyout_at < len(row):
            buyout = parse_money(row[buyout_at])
        terms = ""
        if terms_at is not None and terms_at < len(row):
            terms = cell_text(row[terms_at]).strip()
            pending = pending or row[terms_at].italic
        if not years and buyout is None and not terms:
            continue
        sta = cell_text(row[8]).strip() if len(row) > 8 else ""
        options = cell_text(row[7]).strip() if len(row) > 7 else ""
        players.append(
            {
                "name": name,
                "name_italic": row[1].italic if len(row) > 1 else False,
                "scoresheet_id": cell_text(row[2]).strip() if len(row) > 2 else "",
                "mlb_id": cell_text(row[3]).strip() if len(row) > 3 else "",
                "position": cell_text(row[4]).strip() if len(row) > 4 else "",
                "mlb_org": cell_text(row[5]).strip() if len(row) > 5 else "",
                "mls": cell_text(row[6]).strip() if len(row) > 6 else "",
                "options": options,
                "sta": sta,
                "on_40_man": marker == "1",
                "years": years,
                "buyout": buyout,
                "terms": terms,
                "terms_pending": pending,
            }
        )

    projections, lines = ({}, [])
    if financials_at is not None and year_cols:
        projections, lines = _financials(rows, year_cols, financials_at)

    return {
        "founded": founded_year(rows),
        "summary": _summary(rows),
        "year_columns": [year for year, _index in year_cols],
        "players": players,
        "projections": projections,
        "lines": lines,
    }


def current_summary(parsed, year):
    for entry in parsed.get("summary") or []:
        if entry.get("year") == year:
            return entry
    summary = parsed.get("summary") or []
    return summary[0] if summary else None


def parse_key_sheet(grid):
    """League constants and the division table on the Key tab."""
    rows = normalize(grid)
    season = {}
    header = None
    teams = []
    for row in rows:
        texts = _texts(row)
        for index, text in enumerate(texts):
            cap_match = re.search(r"(\d{4})\s+Salary Cap", text, re.I)
            if cap_match:
                season["year"] = int(cap_match.group(1))
                season["salary_cap"] = _first_money(row[index:])
            if re.search(r"End of IFA", text, re.I):
                season["ifa_deadline"] = _first_date(row[index:])
                if "year" not in season:
                    year_match = re.search(r"(\d{4})", text)
                    if year_match:
                        season["year"] = int(year_match.group(1))
            if re.search(r"\bEOS\b", text):
                season["end_of_season"] = _first_date(row[index:])
        if any(text == "Cap Space" for text in texts) and any("IFA" in text for text in texts):
            header = {text: index for index, text in enumerate(texts) if text}
            continue
        if not header or not texts or not texts[0] or ":" in texts[0]:
            continue
        teams.append(
            {
                "full_name": texts[0],
                "roster_85": _header_money(row, header, "85-Man"),
                "roster_40": _header_money(row, header, "40-Man"),
                "roster_30": _header_money(row, header, "30-Man"),
                "cap_space": _header_money(row, header, "Cap Space"),
                "cash": _header_money(row, header, "$ Reserves"),
                "ifa": _header_money(row, header, "IFA Pool Space"),
            }
        )
    if season.get("year"):
        season["league_min"] = league_minimum(season["year"])
    return {"season": season, "teams": teams}


def parse_service_sheet(grid):
    """The Service Time tab: days on the active roster, on option, and non-roster."""
    rows = normalize(grid)
    header_at = None
    header = {}
    for index, row in enumerate(rows[:5]):
        texts = _texts(row)
        if any(text.upper() == "MLB DAYS" for text in texts):
            header_at = index
            header = {text.upper(): col for col, text in enumerate(texts) if text}
            break
    if header_at is None:
        return []
    records = []
    for row in rows[header_at + 1 :]:
        texts = _texts(row)
        if not any(texts):
            continue
        name = texts[header["NAME"]] if "NAME" in header and header["NAME"] < len(texts) else ""
        if not name or name.upper() == "NAME":
            continue
        records.append(
            {
                "name": name,
                "scoresheet_id": _col(texts, header, "SS#"),
                "mlb_id": _col(texts, header, "MLB#"),
                "mls": _col(texts, header, "MLS"),
                "options": _col(texts, header, "OPT"),
                "sta": _col(texts, header, "STA"),
                "option_used": _bool(_col(texts, header, "OPTION USED?")),
                "mlb_days": _int(_col(texts, header, "MLB DAYS")),
                "option_days": _int(_col(texts, header, "OPTION DAYS")),
                "nonroster_days": _int(_col(texts, header, "NR DAYS")),
                "sos_service_years": _int(_col(texts, header, "SOS SERVICE YEARS")),
                "sos_service_days": _int(_col(texts, header, "SOS SERVICE DAYS")),
            }
        )
    return records


def _col(texts, header, name):
    index = header.get(name)
    if index is None or index >= len(texts):
        return ""
    return texts[index].strip()


def _int(text):
    if text is None or text == "":
        return None
    try:
        return int(str(text).strip())
    except ValueError:
        return None


def _bool(text):
    return str(text).strip().upper() in {"TRUE", "YES", "Y", "1"}


def _first_money(row):
    for cell in row:
        amount = parse_money(cell)
        if amount is not None:
            return amount
    return None


def _first_date(row):
    for cell in row:
        found = parse_date(cell)
        if found:
            return found
    return None


def _header_money(row, header, name):
    index = header.get(name)
    if index is None or index >= len(row):
        return None
    return parse_money(row[index])
