"""Player-level fields from the MLB Stats API.

Season stat lines stay where they are. This module reads the person payload
(height, weight, position, bats, throws, birth date, debut, and current
organization) and writes those columns on ``Player``. The NPL club, contract,
and stat payload are not part of that write.

``load_mlb_rosters`` only walks the season lists, so a player already stored
here who is not on a 2026 roster is never refreshed. ``sync_bios`` updates
every stored MLBID and inserts anyone on this season's affiliated lists who
is missing.
"""

import datetime

from django.utils import timezone

from npl import models
from npl.mlbwatch import MLB_TEAMS
from npl.rosters import position_bucket

# MLB, then each affiliated minor level MLB still publishes. A refused level
# is a skip, not a failed run.
AFFILIATED_SPORTS = (
    (1, "MLB"),
    (11, "AAA"),
    (12, "AA"),
    (13, "A+"),
    (14, "A"),
    (16, "Rookie"),
)

# Columns a refresh is allowed to change. Everything else on Player (the NPL
# club, roster flags, contracts, stats) stays as the league stored it.
BIO_FIELDS = (
    "name",
    "first_name",
    "last_name",
    "birthdate",
    "height",
    "weight",
    "position",
    "bats",
    "throws",
    "mlb_org",
    "roster_status",
    "birth_country",
    "mlb_debut_date",
    "has_appeared_in_majors",
    "active",
    "simple_position",
)

READ_FIELDS = BIO_FIELDS


def index_teams(teams):
    indexed = {}
    for team in teams or []:
        team_id = team.get("id")
        try:
            indexed[int(team_id)] = team
        except (TypeError, ValueError):
            continue
    return indexed


def merge_people(levels):
    """Keep one person per MLBID, preferring the higher level.

    ``levels`` is ``(sport_id, people)`` pairs. A player who appears at MLB
    and again in the minors stays on the MLB row.
    """
    chosen = {}
    for sport_id, people in levels:
        for person in people or []:
            mlb_id = str((person or {}).get("id") or "").strip()
            if not mlb_id:
                continue
            current = chosen.get(mlb_id)
            if current is not None and current[1] < sport_id:
                continue
            chosen[mlb_id] = (person, sport_id)
    return chosen


def _abbrev(team_id):
    try:
        return MLB_TEAMS.get(int(team_id))
    except (TypeError, ValueError):
        return None


def _clip(value, limit):
    text = str(value or "").strip()
    if not text or len(text) > limit:
        return None
    return text


def _weight(value):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0 or number > 999:
        return None
    return str(number)


def _date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _team_ids(person, teams_by_id):
    team = (person or {}).get("currentTeam") or {}
    team_id = team.get("id")
    meta = {}
    try:
        meta = teams_by_id.get(int(team_id)) or {}
    except (TypeError, ValueError):
        meta = {}
    parent_id = team.get("parentOrgId")
    if parent_id in (None, ""):
        parent_id = meta.get("parentOrgId")
    return team_id, parent_id


def bio_values(person, *, sport_id=None, teams_by_id=None, mlb_list_ok=True):
    """Non-stat columns from one person payload.

    Empty strings are left out so a missing height does not wipe a value we
    already stored. ``mlbDebutDate`` is applied when the key is present,
    including a null debut.
    """
    person = person or {}
    teams_by_id = teams_by_id or {}
    values = {}

    first = _clip(person.get("useName") or person.get("firstName"), 255)
    last = _clip(person.get("useLastName") or person.get("lastName"), 255)
    full = _clip(person.get("fullName") or person.get("firstLastName"), 255)
    if first:
        values["first_name"] = first
    if last:
        values["last_name"] = last
    if first and last:
        values["name"] = _clip(f"{first} {last}", 255)
    elif full:
        values["name"] = full

    birthdate = _date(person.get("birthDate"))
    if birthdate:
        values["birthdate"] = birthdate

    height = _clip(person.get("height"), 15)
    if height:
        values["height"] = height
    weight = _weight(person.get("weight"))
    if weight:
        values["weight"] = weight

    position = _clip(((person.get("primaryPosition") or {}).get("abbreviation")), 255)
    if position:
        values["position"] = position
    bats = _clip(((person.get("batSide") or {}).get("code")), 3)
    if bats:
        values["bats"] = bats
    throws = _clip(((person.get("pitchHand") or {}).get("code")), 3)
    if throws:
        values["throws"] = throws

    country = _clip(person.get("birthCountry"), 80)
    if country:
        values["birth_country"] = country

    if "mlbDebutDate" in person:
        debut = _date(person.get("mlbDebutDate"))
        values["mlb_debut_date"] = debut
        values["has_appeared_in_majors"] = debut is not None

    if "active" in person:
        values["active"] = bool(person.get("active"))

    team_id, parent_id = _team_ids(person, teams_by_id)
    org = None
    status = None
    if sport_id == 1:
        org = _abbrev(team_id)
        status = "MLB"
    elif sport_id is not None:
        org = _abbrev(parent_id)
        if mlb_list_ok:
            status = "MINORS"
    elif _abbrev(team_id):
        org = _abbrev(team_id)
        if person.get("active"):
            status = "MLB"
    else:
        org = _abbrev(parent_id)
        if person.get("active") and (org or team_id):
            status = "MINORS"

    if org:
        values["mlb_org"] = org
    if status:
        values["roster_status"] = status
    return values


def _simple_position(position):
    """Group a position the way ``Player.save`` does, with DH kept as DH.

    A full ``save`` also rewrites options and the NPL level, so the refresh
    uses this instead of saving the row.
    """
    probe = models.Player(position=position)
    probe.set_simple_position()
    if probe.simple_position:
        return probe.simple_position
    if (position or "").strip().upper() == "DH":
        return "DH"
    return None


def _group_agrees(simple, position):
    """True when the stored group still describes this MLB position.

    ``SS`` agrees with a shortstop, and ``IF`` agrees with one too. ``P`` does
    not agree with a DH. A matching specific code is left alone so a refresh
    does not collapse SS and CF down to IF and OF.
    """
    if not simple or not position:
        return False
    target = _simple_position(position)
    if not target:
        return False
    if simple == target or simple.upper() == position.upper():
        return True
    return position_bucket(simple) == target or position_bucket(simple) == position_bucket(position)


def _changes(player, values):
    changed = {}
    for field, value in values.items():
        if getattr(player, field) != value:
            changed[field] = value
    source = changed.get("position") or player.position
    simple = _simple_position(source) if source else None
    if simple and not _group_agrees(player.simple_position, source):
        changed["simple_position"] = simple
    return changed


class _Batch:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.rows = []

    def add(self, player, changed):
        if self.dry_run:
            return
        for field, value in changed.items():
            setattr(player, field, value)
        self.rows.append((player, set(changed)))
        if len(self.rows) >= 200:
            self.flush()

    def flush(self):
        if self.dry_run or not self.rows:
            self.rows = []
            return
        now = timezone.now()
        fields = set()
        players = []
        for player, changed in self.rows:
            player.last_modified = now
            fields.update(changed)
            players.append(player)
        fields.add("last_modified")
        models.Player.objects.bulk_update(players, sorted(fields), batch_size=200)
        self.rows = []


def sync_bios(
    listed,
    teams_by_id,
    fetch_people,
    *,
    mlb_list_ok=True,
    create=True,
    dry_run=False,
    only_ids=None,
    limit=None,
    log=None,
):
    """Update stored players and insert season-list players we do not have.

    ``listed`` maps an MLBID to ``(person, sport_id)``. ``fetch_people`` is
    called with the stored ids that were not on those lists and returns
    ``(people_by_id, missing_ids)``. Ids MLB refuses are counted and left
    unchanged. Returns a count dict.
    """
    only_ids = {str(mlb_id).strip() for mlb_id in only_ids} if only_ids else None
    if only_ids is not None:
        only_ids = {mlb_id for mlb_id in only_ids if mlb_id}

    players = list(models.Player.objects.all().only(*READ_FIELDS))
    by_id = {}
    for player in players:
        mlb_id = str(player.mlb_id)
        if only_ids is not None and mlb_id not in only_ids:
            continue
        by_id[mlb_id] = player

    on_a_list = set(listed)
    if limit is not None and only_ids is None:
        listed = dict(list(listed.items())[:limit])

    counts = {
        "updated": 0,
        "unchanged": 0,
        "created": 0,
        "skipped": 0,
        "not_found": 0,
        "unresolved": 0,
    }
    batch = _Batch(dry_run)
    seen = set()

    def note(mlb_id, player_name, action, fields):
        if log:
            detail = ", ".join(sorted(fields)) if fields else action
            log(f"{mlb_id} {player_name}: {detail}")

    def write_update(player, person, sport_id):
        values = bio_values(
            person,
            sport_id=sport_id,
            teams_by_id=teams_by_id,
            mlb_list_ok=mlb_list_ok,
        )
        changed = _changes(player, values)
        if not changed:
            counts["unchanged"] += 1
            return
        batch.add(player, changed)
        counts["updated"] += 1
        note(player.mlb_id, values.get("name") or player.name, "updated", changed)

    def write_create(mlb_id, person, sport_id):
        values = bio_values(
            person,
            sport_id=sport_id,
            teams_by_id=teams_by_id,
            mlb_list_ok=mlb_list_ok,
        )
        name = values.get("name")
        if not name:
            counts["skipped"] += 1
            return
        if not dry_run:
            player = models.Player(mlb_id=str(mlb_id), name=name)
            for field, value in values.items():
                setattr(player, field, value)
            player.save()
        counts["created"] += 1
        note(mlb_id, name, "created", values)

    def room():
        return limit is None or counts["updated"] + counts["created"] < limit

    for mlb_id, (person, sport_id) in listed.items():
        if only_ids is not None and mlb_id not in only_ids:
            continue
        if not room():
            break
        seen.add(mlb_id)
        player = by_id.get(mlb_id)
        if player is None:
            if create:
                write_create(mlb_id, person, sport_id)
            continue
        write_update(player, person, sport_id)

    need_people = [
        mlb_id
        for mlb_id in by_id
        if mlb_id not in seen and mlb_id not in on_a_list and str(mlb_id).isdigit()
    ]
    if only_ids is not None and create:
        for mlb_id in sorted(only_ids):
            if mlb_id in seen or mlb_id in by_id or not mlb_id.isdigit():
                continue
            if mlb_id not in need_people:
                need_people.append(mlb_id)
    nondigit = [
        mlb_id for mlb_id in by_id if mlb_id not in seen and not str(mlb_id).isdigit()
    ]
    counts["unresolved"] += len(nondigit)

    if limit is not None:
        remaining = limit - (counts["updated"] + counts["created"])
        need_people = need_people[: max(remaining, 0)]

    if need_people and room():
        found, missing = fetch_people(need_people)
        found = {str(mlb_id): person for mlb_id, person in (found or {}).items()}
        missing = {str(mlb_id) for mlb_id in (missing or set())}
        for mlb_id in need_people:
            if not room():
                break
            person = found.get(mlb_id)
            if person is None:
                if mlb_id in missing:
                    counts["not_found"] += 1
                else:
                    counts["unresolved"] += 1
                continue
            player = by_id.get(mlb_id)
            if player is None:
                write_create(mlb_id, person, None)
            else:
                write_update(player, person, None)

    batch.flush()
    return counts
