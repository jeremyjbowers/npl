"""Franchise numbers are stable. Club names are not.

The roster workbook tabs are the authority for the current nickname and the
number (`Rats #8`, `GmbH #13`). Older transaction logs use earlier names for
the same number. A few spellings show up only on those logs.
"""

import re

from django.db.models import Q

# Number, then every name that has meant that franchise. The first name is
# the current roster-tab nickname.
FRANCHISES = {
    1: ["Cheddar", "Cheesequake Cheddar", "Nose Pickers", "Schwartzstops"],
    2: ["Valkyries", "New York Valkyries", "geekSquad", "Blazing Fastballl", "Schrodinger's Bats"],
    3: ["Speedsters", "Central City Speedsters", "Big Sky MoneyBaller$", "D.C. Frank Underwoods"],
    4: ["Perwar", "Dallas Perwar", "MIT Beavers", "South Austin Armadillos", "Northshore Killer Machines"],
    5: [
        "DockHounds",
        "Dockhounds",
        "Milwaukee DockHounds",
        "Hyperjets",
        "Planet Druidia Hyperjets",
        "B42s",
        "Brooklyn 42s",
        "Rochester Reapers",
    ],
    6: ["King", "Lion King", "Hydra", "Sound Hydra", "Acworth Aces", "Ritchie's Rejects"],
    7: ["Kodiaks", "Chicago Kodiaks", "Lethal Weapon", "Bad News Bears", "San Diego Coasters"],
    8: ["Rats", "Sickos", "Absolute Sickos", "High Hard Ones", "Carl Spacklers"],
    9: ["Bears", "Denver Bears", "Field of Dreams", "Delaware Werechickens"],
    10: [
        "TOOTBLANs",
        "TOOTBLANS",
        "Brooklyn TOOTBLANs",
        "Texas Schoolbook Depository",
        "Villanova Corks",
        "New Ulm Eagles",
        "New York Appleaters",
    ],
    11: ["Orphans", "Chicago Orphans", "Ryne", "Non, Je Ne Regrette Ryne", "Gatherers", "Hunter Gatherers"],
    12: ["Ducksnorts", "Midwest Ducksnorts", "California Billy Goats", "Up For Grabs", "Good Wood", "Win One For The Chipper"],
    13: [
        "GmbH",
        "GMBH",
        "Nuremberg GmbH",
        "Nuremberg, GmbH",
        "Defenestrations",
        "Defenestrations of Prague",
        "Prague",
        "Rabbits",
    ],
    14: ["Hitmen", "Honolulu Hitmen", "Monterey Grizzlies"],
    15: ["Tobacconists", "Tobacconoists", "Durham Tobacconists", "Boston Tea Party", "Christian Missionaries"],
    16: ["Quails", "Qualis", "Quebec Quails", "Vegas Vig", "Rotowire"],
    17: ["Calling", "London Calling", "Majority WHIP"],
    18: ["Bulldog", "Los Angeles Bulldog"],
    19: ["Ropes", "Frozen Ropes", "Denver Diamonds"],
    20: ["Starks", "Winterfell Starks", "Amish Rakefight", "Oregon Reigning Kings"],
    21: ["Guys", "Bad Guys", "Humongous Melonheads", "Country Rubes"],
    22: ["McFlys", "Mcflys", "Hill Valley McFlys", "Minneapolis Machines", "Rhode Island Reds", "North Texas Heat"],
    23: ["Bosses", "Asbury Park Bosses", "Spanish Fly Swatters", "Victorian Sex Rebels", "Orlando Juice"],
    24: ["Villagers", "Old Sturbridge Villagers", "RJs Bird Killers", "Orland Park Puds"],
}


def normalize_club(label):
    if label is None:
        return ""
    text = str(label).strip().lower().replace("&", " and ")
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9#]+", " ", text)
    return " ".join(text.split())


def _alias_index():
    index = {}
    for number, names in FRANCHISES.items():
        index[normalize_club(f"{names[0]} #{number}")] = number
        index[normalize_club(f"#{number}")] = number
        for name in names:
            index[normalize_club(name)] = number
    return index


ALIASES = _alias_index()


def franchise_number(label):
    """Return 1-24 for a club name, or None when the label is not a club."""
    key = normalize_club(label)
    if not key or key in {"-", "phi"}:
        return None
    numbered = re.search(r"#\s*(\d{1,2})$", key)
    if numbered:
        number = int(numbered.group(1))
        if number in FRANCHISES:
            return number
    if key in ALIASES:
        return ALIASES[key]
    return None


def tab_id_for(number):
    return f"{FRANCHISES[number][0]} #{number}"


def team_for_label(label):
    """Match a historical or current name to the Team row for that franchise."""
    from npl.models import Team

    number = franchise_number(label)
    if number is None:
        return None
    suffix = f"#{number}"
    team = Team.objects.filter(tab_id__endswith=suffix).first()
    if team:
        return team
    names = {normalize_club(name) for name in FRANCHISES[number]}
    names.add(normalize_club(FRANCHISES[number][0]))
    for team in Team.objects.all():
        if normalize_club(team.short_name) in names or normalize_club(team.full_name) in names:
            return team
        if team.tab_id and team.tab_id.strip().endswith(suffix):
            return team
    return Team.objects.filter(
        Q(short_name__iexact=FRANCHISES[number][0]) | Q(full_name__iexact=FRANCHISES[number][0])
    ).first()
