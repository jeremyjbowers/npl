"""MLB Stats API checks, keyed by MLBID.

The FanGraphs loaders in the management commands join on ``fg_id``. This
league's players are keyed by ``mlb_id``, and a debut is a field on the
people endpoint rather than a row in a season stat dump. Season lines still
land in the same stats dictionary the FanGraphs loader writes
(``{year}_majors_hit`` and ``{year}_majors_pitch``).

The same pass reads the signing and minor-league seasons used to decide
whether the IFA button is shown.
"""

import datetime
import json
from urllib.parse import urlencode

import requests
from django.utils import timezone

from npl import ifa, models

# Year-by-year lines used for the stateside-year and NPB/KBO counts.
IFA_SPORT_IDS = (11, 12, 13, 14, 15, 16, 31, 32)

PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
STATS_URL = "https://statsapi.mlb.com/api/v1/stats"
PEOPLE_CHUNK = 50
# Signing histories are large. A 50-player hydrate is refused with HTTP 406.
TRANSACTIONS_CHUNK = 10
# Datacenter calls are sometimes refused until the request looks like a browser.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

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
    """GET a stats API URL.

    The first attempt is a plain request. A 406 is retried once with a browser
    user agent. Forcing ``Accept: application/json`` is itself a 406 on some
    MLB edges, so that header is not sent.
    """
    response = requests.get(url, timeout=30)
    if response.status_code == 406:
        response = requests.get(
            url,
            headers={"User-Agent": BROWSER_UA, "Accept": "*/*"},
            timeout=30,
        )
    response.raise_for_status()
    return response.json()


def _chunks(values, size):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def people_url(mlb_ids, hydrate="currentTeam"):
    query = urlencode(
        {
            "personIds": ",".join(str(mlb_id) for mlb_id in mlb_ids),
            "hydrate": hydrate,
        }
    )
    return f"{PEOPLE_URL}?{query}"


def _person_path_url(mlb_id, hydrate):
    return f"{PEOPLE_URL}/{mlb_id}?{urlencode({'hydrate': hydrate})}"


def _fetch_map(mlb_ids, hydrate, getter):
    """Return ``(people_by_id, missing_ids)``.

    ``missing_ids`` were absent from a successful response. A refused batch is
    split and retried. One player is also tried at ``/people/{id}`` before he
    is given up. An id that still fails is in neither set.
    """
    ids = [str(mlb_id) for mlb_id in mlb_ids if mlb_id]
    if not ids:
        return {}, set()
    urls = [people_url(ids, hydrate=hydrate)]
    if len(ids) == 1:
        urls.append(_person_path_url(ids[0], hydrate))
    payload = None
    for url in urls:
        try:
            payload = getter(url)
            break
        except Exception:
            payload = None
    if payload is None:
        if len(ids) == 1:
            return {}, set()
        mid = len(ids) // 2
        left, left_missing = _fetch_map(ids[:mid], hydrate, getter)
        right, right_missing = _fetch_map(ids[mid:], hydrate, getter)
        left.update(right)
        return left, left_missing | right_missing
    found = {str(person.get("id")): person for person in payload.get("people") or []}
    return found, set(ids) - set(found)


def _merge_transactions(people, mlb_ids, getter):
    ids = [str(mlb_id) for mlb_id in mlb_ids if mlb_id]
    for group in _chunks(ids, TRANSACTIONS_CHUNK):
        fetched, _missing = _fetch_map(group, "transactions", getter)
        for pid, person in fetched.items():
            target = people.get(pid)
            if target is None or "transactions" not in person:
                continue
            target["transactions"] = person.get("transactions") or []


def _attach_career_stats(people, mlb_ids, getter):
    """Merge minor-league, NPB, and KBO year lines onto these people payloads.

    A player is ready only when every sport came back and his signing list did
    too. One refused player does not drop the rest of the chunk.
    """
    ids = [str(mlb_id) for mlb_id in mlb_ids if mlb_id]
    if not ids or not people:
        return
    seen = {pid: set() for pid in ids}
    for sport_id in IFA_SPORT_IDS:
        hydrate = f"stats(group=[hitting,pitching],type=[yearByYear],sportId={sport_id})"
        fetched, _missing = _fetch_map(ids, hydrate, getter)
        for pid, person in fetched.items():
            target = people.get(pid)
            if target is None:
                continue
            seen.setdefault(pid, set()).add(sport_id)
            target.setdefault("stats", [])
            target["stats"].extend(person.get("stats") or [])
    needed = set(IFA_SPORT_IDS)
    for pid in ids:
        person = people.get(pid)
        if person is None:
            continue
        if seen.get(pid) == needed and "transactions" in person:
            person["_ifa_ready"] = True


def fetch_people(mlb_ids, getter=None):
    """Return ``(people_by_id, missing_ids)`` from the people endpoint.

    Debut and club use the current-team hydrate. Signing histories are separate.
    A 406 on a batch is split down to one player instead of aborting the run.
    ``missing_ids`` are ids MLB answered for and does not have.
    """
    getter = getter or default_getter
    found = {}
    missing = set()
    for chunk in _chunks([mlb_id for mlb_id in mlb_ids if mlb_id], PEOPLE_CHUNK):
        chunk_people, gone = _fetch_map(chunk, "currentTeam", getter)
        missing.update(gone)
        _merge_transactions(chunk_people, chunk, getter)
        _attach_career_stats(chunk_people, chunk, getter)
        found.update(chunk_people)
    return found, missing


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
    """Update debut, club, and IFA facts for these players. Returns how many were saved."""
    getter = getter or default_getter
    now = now or timezone.now()
    players = list(players)
    people, missing = fetch_people([player.mlb_id for player in players], getter=getter)
    saved = 0
    for player in players:
        person = people.get(str(player.mlb_id))
        if person is None:
            if str(player.mlb_id) in missing:
                player.mlb_status_checked = now
                player.save(update_fields=["mlb_status_checked"])
            continue
        apply_person(player, person, now=now)
        fields = [
            "mlb_debut_date",
            "has_appeared_in_majors",
            "mlb_org",
            "roster_status",
            "mlb_status_checked",
        ]
        fields.extend(ifa.apply_player_facts(player, person, now))
        player.save(update_fields=fields)
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
