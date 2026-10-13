"""Who can be nominated for international free agency.

Amateur Acquisition says an IFA player must:

- be under 25 on January 1 of the year that IFA period begins
- be unowned now, and never have been owned by an NPL club
- have fewer than three seasons in NPB or KBO
- already be signed by an MLB club as an international free agent
- not have played in an affiliated stateside minor league in more than one
  calendar year (the Dominican and Venezuelan summer leagues do not count)

A signing that was a major-league contract is offseason free agency, not IFA.
A player who has appeared in the majors is a free-agent nomination, not IFA.
Facts that have not been read from MLB yet are not treated as eligible.
"""

import datetime

# Residents of these countries are Rule 4 draft-eligible, not international amateurs.
RULE4_COUNTRIES = frozenset(
    {
        "usa",
        "u.s.",
        "u.s.a.",
        "united states",
        "united states of america",
        "canada",
        "puerto rico",
        "guam",
        "american samoa",
        "u.s. virgin islands",
        "us virgin islands",
        "virgin islands",
        "northern mariana islands",
    }
)

# Full-season affiliated levels. Rookie ball is handled by league, because
# that sport also contains the Dominican and Venezuelan summer leagues.
STATESIDE_SPORT_IDS = frozenset({11, 12, 13, 14, 15})
ROOKIE_SPORT_ID = 16
SUMMER_LEAGUE_IDS = frozenset({130, 134})  # DSL, VSL
NPB_KBO_SPORT_IDS = frozenset({31, 32})

NOT_CHECKED = (
    "International free-agent eligibility has not been checked yet, "
    "so this player cannot be nominated for IFA."
)
MISSING_BIRTHDATE = "Birthdate is missing, so the international free-agent age rule cannot be checked."
MISSING_COUNTRY = "Birth country is missing, so international signing status cannot be confirmed."
NOT_INTERNATIONAL = "This player was not signed by an MLB club as an international free agent."
MAJOR_LEAGUE_CONTRACT = (
    "This player signed a major-league contract and is available in offseason free agency, not IFA."
)
MISSING_SIGNING_DATE = "This player has no international signing date on file."
NOT_SIGNED_YET = "This player had not signed with an MLB club yet."
PREVIOUSLY_OWNED = (
    "This player was owned by an NPL club before, so he is eligible for the Rule 4 draft "
    "rather than international free agency."
)
TOO_MANY_STATESIDE = "This player has played in a stateside minor league in more than one calendar year."
TOO_MANY_FOREIGN = "This player has three or more seasons in NPB or KBO."
APPEARED_IN_MAJORS = "This player has appeared in the majors. Use the free-agent nomination."
DEBUT_UNCHECKED = (
    "Majors debut has not been checked yet, so this player cannot be nominated for an IFA auction."
)


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def ifa_year(season, today):
    """Calendar year whose January 1 is the age date for the open IFA period.

    The period begins after New Year's of the season it feeds. A stored
    deadline is the end of that period: before it, use that year; after it,
    the next period has not started and belongs to the following year.
    """
    if season is None:
        return today.year if today.month < 7 else today.year + 1
    deadline = getattr(season, "ifa_deadline", None)
    if deadline:
        return deadline.year if today <= deadline else deadline.year + 1
    opening = getattr(season, "opening_day", None)
    if opening and today < opening:
        return season.year
    phase = getattr(season, "phase", None)
    if phase == "offseason" and opening is None and today.month < 7:
        return season.year
    return season.year + 1


def under_25(birthdate, year):
    """True when he has not turned 25 on January 1 of ``year``."""
    if birthdate is None:
        return False
    return birthdate > datetime.date(year - 25, 1, 1)


def _whole(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _played(split):
    stat = split.get("stat") or {}
    return _whole(stat.get("gamesPlayed")) >= 1 or _whole(stat.get("gamesPitched")) >= 1


def _id(value):
    if isinstance(value, dict):
        value = value.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def seasons_from_stats(stats):
    """Return ``(stateside_years, npb_kbo_seasons)`` from year-by-year splits.

    A calendar year counts once, and only if he played at least one game.
    Complex and full-season U.S. leagues count. DSL and VSL do not. A rookie
    line with no league id is an aggregate and is ignored.
    """
    stateside = set()
    foreign = set()
    for block in stats or []:
        if not isinstance(block, dict):
            continue
        splits = block.get("splits") if "splits" in block else None
        if splits is None and block.get("season"):
            splits = [block]
        for split in splits or []:
            if not isinstance(split, dict) or not _played(split):
                continue
            year = _whole(split.get("season"))
            if not year:
                continue
            sport = _id(split.get("sport"))
            league = _id(split.get("league"))
            if sport in NPB_KBO_SPORT_IDS:
                foreign.add(year)
            elif sport in STATESIDE_SPORT_IDS:
                stateside.add(year)
            elif sport == ROOKIE_SPORT_ID and league and league not in SUMMER_LEAGUE_IDS:
                stateside.add(year)
    return len(stateside), len(foreign)


def _is_signing(transaction):
    code = (transaction.get("typeCode") or "").upper()
    description = (transaction.get("description") or "").lower()
    if code in {"SFA", "SGN"}:
        return True
    return "signed free agent" in description or "signed as a free agent" in description


def classify_signing(transactions, birth_country):
    """The first MLB signing, and whether it was an international free agent.

    ``SGN`` without "free agent" is a Rule 4 signing. ``SFA`` is a free-agent
    signing; it is international only when his birth country is outside the
    Rule 4 countries. ``international`` is None when a free-agent signing has
    no birth country to classify.
    """
    signings = [row for row in transactions or [] if isinstance(row, dict) and _is_signing(row)]
    signings.sort(key=lambda row: parse_date(row.get("date")) or datetime.date.max)
    if not signings:
        return {"international": False, "date": None, "major_league_contract": False}
    first = signings[0]
    description = (first.get("description") or "").lower()
    code = (first.get("typeCode") or "").upper()
    free_agent = code == "SFA" or "free agent" in description
    major = "major league contract" in description or "major-league contract" in description
    signed_on = parse_date(first.get("date"))
    if not free_agent:
        return {"international": False, "date": signed_on, "major_league_contract": major}
    country = (birth_country or "").strip().casefold()
    if not country:
        return {"international": None, "date": signed_on, "major_league_contract": major}
    if country in RULE4_COUNTRIES:
        return {"international": False, "date": signed_on, "major_league_contract": major}
    return {"international": True, "date": signed_on, "major_league_contract": major}


def _signed_in_time(signing_date, today):
    """Whether an MLB club had already signed him as of ``today``.

    The rules include the most recent international class and anyone signed
    before it. The league does not store the morning the NPL period opens, so
    a signing on or before today is in time.
    """
    if signing_date is None:
        return False, MISSING_SIGNING_DATE
    if signing_date > today:
        return False, NOT_SIGNED_YET
    return True, ""


def eligibility(player, season, today, previously_owned=False):
    """Return ``(eligible, reason)``. The regular-season window is separate."""
    if previously_owned:
        return False, PREVIOUSLY_OWNED
    debut = player.has_appeared_in_majors
    if debut is True:
        return False, APPEARED_IN_MAJORS
    if debut is None:
        return False, DEBUT_UNCHECKED
    birthdate = getattr(player, "birthdate", None)
    if not birthdate:
        return False, MISSING_BIRTHDATE
    year = ifa_year(season, today)
    if not under_25(birthdate, year):
        return False, (
            f"This player is not under 25 on January 1, {year}, "
            "so he is not eligible for international free agency."
        )
    if not getattr(player, "ifa_checked", None):
        return False, NOT_CHECKED
    signee = player.international_signee
    if signee is None:
        return False, MISSING_COUNTRY
    if not signee:
        return False, NOT_INTERNATIONAL
    if player.international_mlb_contract:
        return False, MAJOR_LEAGUE_CONTRACT
    in_time, timing = _signed_in_time(player.international_signing_date, today)
    if not in_time:
        return False, timing
    if player.npb_kbo_seasons is None or player.stateside_seasons is None:
        return False, NOT_CHECKED
    if player.npb_kbo_seasons >= 3:
        return False, TOO_MANY_FOREIGN
    if player.stateside_seasons > 1:
        return False, TOO_MANY_STATESIDE
    return True, ""


def apply_player_facts(player, person, now):
    """Copy signing and season facts onto ``player``. Return the fields to save.

    An empty list means this payload did not include a finished check.
    """
    if not person or not person.get("_ifa_ready") or "transactions" not in person:
        return []
    country = (person.get("birthCountry") or "")[:80]
    stateside, foreign = seasons_from_stats(person.get("stats") or [])
    signing = classify_signing(person.get("transactions") or [], country)
    fields = [
        "birth_country",
        "stateside_seasons",
        "npb_kbo_seasons",
        "international_signee",
        "international_signing_date",
        "international_mlb_contract",
        "ifa_checked",
    ]
    player.birth_country = country
    player.stateside_seasons = stateside
    player.npb_kbo_seasons = foreign
    player.international_signee = signing["international"]
    player.international_signing_date = signing["date"]
    player.international_mlb_contract = signing["major_league_contract"]
    player.ifa_checked = now
    birthdate = parse_date(person.get("birthDate"))
    if birthdate:
        player.birthdate = birthdate
        fields.append("birthdate")
    return fields
