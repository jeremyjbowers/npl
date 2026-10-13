"""MLB Stats API checks, keyed by MLBID.

The FanGraphs loaders in the management commands join on ``fg_id``. This
league's players are keyed by ``mlb_id``, and a debut is a field on the
people endpoint rather than a row in a season stat dump. Season lines still
land in the same stats dictionary the FanGraphs loader writes
(``{year}_majors_hit`` and ``{year}_majors_pitch``).
"""

import datetime
import json
from urllib.parse import urlencode

import requests
from django.utils import timezone

from npl import models

PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
STATS_URL = "https://statsapi.mlb.com/api/v1/stats"
PEOPLE_CHUNK = 50

# sportId=1 clubs. Abbreviation is not on the hydrated person payload.
MLB_TEAMS = {
    108: "LAA",
    109: "AZ",
    110: "BAL",
    111: "BOS",
    112: "CHC",
    113: "CIN",
    114: "CLE",
    115: "COL",
    116: "DET",
    117: "HOU",
    118: "KC",
    119: "LAD",
    120: "WSH",
    121: "NYM",
    133: "ATH",
    134: "PIT",
    135: "SD",
    136: "SEA",
    137: "SF",
    138: "STL",
    139: "TB",
    140: "TEX",
    141: "TOR",
    142: "MIN",
    143: "PHI",
    144: "ATL",
    145: "CWS",
    146: "MIA",
    147: "NYY",
    158: "MIL",
}


def default_getter(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def _chunks(values, size):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def people_url(mlb_ids):
    query = urlencode(
        {
            "personIds": ",".join(str(mlb_id) for mlb_id in mlb_ids),
            "hydrate": "currentTeam",
        }
    )
    return f"{PEOPLE_URL}?{query}"


def fetch_people(mlb_ids, getter=None):
    """Return ``{mlb_id: person}`` from the people endpoint."""
    getter = getter or default_getter
    found = {}
    for chunk in _chunks([mlb_id for mlb_id in mlb_ids if mlb_id], PEOPLE_CHUNK):
        payload = getter(people_url(chunk))
        for person in payload.get("people") or []:
            found[str(person.get("id"))] = person
    return found


def apply_person(player, person, now=None):
    """Set debut, majors flag, and current MLB club from one people payload."""
    now = now or timezone.now()
    debut = (person or {}).get("mlbDebutDate") or ""
    if debut:
        player.mlb_debut_date = datetime.date.fromisoformat(str(debut)[:10])
        player.has_appeared_in_majors = True
    else:
        player.mlb_debut_date = None
        player.has_appeared_in_majors = False
    current = (person or {}).get("currentTeam") or {}
    abbreviation = MLB_TEAMS.get(current.get("id"))
    if abbreviation:
        player.mlb_org = abbreviation
        player.roster_status = "MLB"
    elif current.get("id"):
        player.roster_status = "MINORS"
    player.mlb_status_checked = now
    return player


def refresh_appearances(players, getter=None, now=None):
    """Update debut and club for these players. Returns how many were saved."""
    getter = getter or default_getter
    now = now or timezone.now()
    players = list(players)
    people = fetch_people([player.mlb_id for player in players], getter=getter)
    saved = 0
    for player in players:
        person = people.get(str(player.mlb_id))
        if person is None:
            player.mlb_status_checked = now
            player.save(update_fields=["mlb_status_checked"])
            continue
        apply_person(player, person, now=now)
        player.save(
            update_fields=[
                "mlb_debut_date",
                "has_appeared_in_majors",
                "mlb_org",
                "roster_status",
                "mlb_status_checked",
            ]
        )
        saved += 1
    return saved


def appearance_batch(limit=200):
    """Players never checked, then the ones checked longest ago."""
    from django.db.models import F

    return models.Player.objects.exclude(mlb_id="").order_by(
        F("mlb_status_checked").asc(nulls_first=True),
        "mlb_id",
    )[:limit]


def stats_url(group, season, offset, limit):
    query = urlencode(
        {
            "stats": "season",
            "group": group,
            "season": season,
            "sportId": 1,
            "limit": limit,
            "offset": offset,
        }
    )
    return f"{STATS_URL}?{query}"


def fetch_season_splits(group, season, getter=None, page_size=2000):
    getter = getter or default_getter
    offset = 0
    collected = []
    while True:
        payload = getter(stats_url(group, season, offset, page_size))
        splits = []
        for block in payload.get("stats") or []:
            splits.extend(block.get("splits") or [])
        collected.extend(splits)
        if len(splits) < page_size:
            break
        offset += page_size
    return collected


def _whole(value):
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _rate(value):
    if value in (None, ""):
        return None
    text = str(value).strip().lstrip(".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _innings(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    if "." in text:
        whole, fraction = text.split(".", 1)
        thirds = _whole(fraction[:1])
        return _whole(whole) + min(thirds, 2) / 3.0
    return float(_whole(text))


def hitting_stats(split, season):
    stat = split.get("stat") or {}
    return {
        "year": int(season),
        "type": "majors",
        "level": "mlb",
        "side": "hit",
        "slug": f"{season}_majors_hit",
        "plate_appearances": _whole(stat.get("plateAppearances")),
        "ab": _whole(stat.get("atBats")),
        "hits": _whole(stat.get("hits")),
        "hr": _whole(stat.get("homeRuns")),
        "sb": _whole(stat.get("stolenBases")),
        "runs": _whole(stat.get("runs")),
        "rbi": _whole(stat.get("rbi")),
        "bb": _whole(stat.get("baseOnBalls")),
        "k": _whole(stat.get("strikeOuts")),
        "avg": _rate(stat.get("avg")),
        "obp": _rate(stat.get("obp")),
        "slg": _rate(stat.get("slg")),
        "g": _whole(stat.get("gamesPlayed")),
    }


def pitching_stats(split, season):
    stat = split.get("stat") or {}
    innings = _innings(stat.get("inningsPitched"))
    strikeouts = _whole(stat.get("strikeOuts"))
    walks = _whole(stat.get("baseOnBalls"))
    row = {
        "year": int(season),
        "type": "majors",
        "level": "mlb",
        "side": "pitch",
        "slug": f"{season}_majors_pitch",
        "g": _whole(stat.get("gamesPitched") or stat.get("gamesPlayed")),
        "gs": _whole(stat.get("gamesStarted")),
        "ip": round(innings, 3) if innings else 0,
        "k": strikeouts,
        "bb": walks,
        "era": _rate(stat.get("era")),
        "ha": _whole(stat.get("hits")),
        "hra": _whole(stat.get("homeRuns")),
        "er": _whole(stat.get("earnedRuns")),
    }
    if innings:
        row["k_9"] = round(strikeouts * 9 / innings, 2)
        row["bb_9"] = round(walks * 9 / innings, 2)
    return row


def store_splits(splits, side, season):
    """Write one season side onto the players we already have. Returns the count."""
    builder = hitting_stats if side == "hit" else pitching_stats
    by_id = {}
    for split in splits:
        player = split.get("player") or {}
        mlb_id = player.get("id")
        if mlb_id is None:
            continue
        by_id[str(mlb_id)] = split
    if not by_id:
        return 0
    saved = 0
    for player in models.Player.objects.filter(mlb_id__in=list(by_id)):
        row = builder(by_id[str(player.mlb_id)], season)
        if side == "hit" and row["plate_appearances"] < 1:
            continue
        if side == "pitch" and row["g"] < 1:
            continue
        player.set_stats(row)
        if player.has_appeared_in_majors is not True:
            player.has_appeared_in_majors = True
        player.save(update_fields=["stats", "has_appeared_in_majors"])
        saved += 1
    return saved


def load_season_stats(season, getter=None):
    """Load this season's MLB hitting and pitching for players we know."""
    hitting = fetch_season_splits("hitting", season, getter=getter)
    pitching = fetch_season_splits("pitching", season, getter=getter)
    return {
        "hitting": store_splits(hitting, "hit", season),
        "pitching": store_splits(pitching, "pitch", season),
    }


def read_state(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def write_state(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
