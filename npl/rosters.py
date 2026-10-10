"""Split one team roster into the sections the team page renders.

The team page used to run a separate query per list (MLB, each injured
list, each minor-league level). Callers now load the club once and use
these helpers to slice that list in memory.
"""

SECTION_SPECS = (
    ("mlb", "MLB Roster", "mlb-roster"),
    ("roster_7dayIL", "7-Day IL", "roster-7dayIL"),
    ("roster_56dayIL", "56-Day IL", "roster-56dayIL"),
    ("roster_eosIL", "End of Season IL", "roster-eosIL"),
    ("roster_restricted", "Restricted List", "roster-restricted"),
    ("roster_foreign", "Foreign List", "roster-foreign"),
    ("roster_outrighted", "Outrighted", "roster-outrighted"),
    ("roster_nonroster", "Non-Roster", "roster-nonroster"),
    ("roster_tripleA", "AAA Roster", "aaa-roster"),
    ("roster_tripleA_option", "AAA Roster (On Option)", "aaa-option-roster"),
    ("roster_doubleA", "AA Roster", "aa-roster"),
    ("roster_singleA", "A Roster", "a-roster"),
)

# A 40-man player on any of these lists is not on the active MLB roster.
MLB_BLOCKERS = (
    "roster_tripleA",
    "roster_tripleA_option",
    "roster_7dayIL",
    "roster_56dayIL",
    "roster_eosIL",
    "roster_restricted",
    "roster_outrighted",
    "roster_foreign",
    "roster_retired",
    "roster_nonroster",
    "roster_doubleA",
    "roster_singleA",
)

_PITCHERS = {"P", "SP", "RP", "LHP", "RHP", "SR"}
_CATCHERS = {"C", "CA"}
_INFIELD = {"IF", "1B", "2B", "3B", "SS"}
_OUTFIELD = {"OF", "CF", "LF", "RF"}


def position_bucket(simple_position):
    pos = (simple_position or "").upper()
    if pos in _PITCHERS:
        return "P"
    if pos in _CATCHERS:
        return "C"
    if pos in _INFIELD:
        return "IF"
    if pos in _OUTFIELD:
        return "OF"
    return "UT"


def is_active_mlb(player):
    if not getattr(player, "roster_40man", False):
        return False
    return not any(getattr(player, flag, False) for flag in MLB_BLOCKERS)


def _invert(value):
    """Reverse a string so an ascending sort matches a database DESC."""
    text = "" if value is None else str(value)
    return "".join(chr(0x10FFFF - ord(ch)) for ch in text)


def _service_key(player):
    return (
        _invert(getattr(player, "mls_time", None)),
        getattr(player, "mls_year", None) or "",
        getattr(player, "last_name", None) or "",
    )


def order_players(players):
    """Pitchers first, then hitters by position. Service time breaks ties."""
    pitchers = []
    hitters = []
    for player in players:
        if position_bucket(player.simple_position) == "P":
            pitchers.append(player)
        else:
            hitters.append(player)
    pitchers.sort(key=lambda player: ((player.simple_position or ""),) + _service_key(player))
    hitters.sort(key=lambda player: ((player.simple_position or ""),) + _service_key(player))
    return pitchers + hitters


def build_sections(players):
    grouped = {key: [] for key, _title, _anchor in SECTION_SPECS}
    for player in players:
        if is_active_mlb(player):
            grouped["mlb"].append(player)
        for key, _title, _anchor in SECTION_SPECS:
            if key != "mlb" and getattr(player, key, False):
                grouped[key].append(player)

    sections = []
    for key, title, anchor in SECTION_SPECS:
        members = grouped[key]
        if not members:
            continue
        sections.append(
            {
                "key": key,
                "title": title,
                "anchor": anchor,
                "players": order_players(members),
            }
        )
    return sections


def summarize(players):
    counts = {"C": 0, "IF": 0, "OF": 0, "P": 0, "UT": 0}
    for player in players:
        counts[position_bucket(getattr(player, "simple_position", None))] += 1
    return {
        "total_count": len(players),
        "roster_40_man_count": sum(1 for player in players if getattr(player, "roster_40man", False)),
        "pos_counts": counts,
    }
