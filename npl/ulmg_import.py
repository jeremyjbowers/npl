"""Copy roster status, affiliate level, and season stats from ULMG into NPL.

Each ULMG PlayerStatSeason becomes an NPL PlayerStatSeason. The current roster
line is also copied onto the player so the roster tables can show it. This
module reads ULMG once. It does not create players and it does not query ULMG
while a page is rendering.
"""

import json
import os

from django.db import connections

from npl import models, utils

STATUS_FIELDS = (
    "roster_status",
    "mlb_org",
    "fg_role",
    "fg_role_type",
    "fg_injury_description",
    "fg_is_mlb40man",
    "fg_is_injured",
    "fg_is_starter",
    "fg_is_bench",
    "fg_id",
    "bats",
    "throws",
    "has_appeared_in_majors",
)

MINORS_LEVELS = {"AAA", "AA", "A+", "A", "A-"}
ROOKIE_LEVELS = {"RK", "RK2", "SS", "ROOKIE", "R"}

FETCH_SQL = """
    SELECT
        p.id AS player_id,
        TRIM(p.mlbam_id) AS mlbam_id,
        TRIM(p.fg_id) AS fg_id,
        p.current_mlb_org AS current_mlb_org,
        p.bats AS bats,
        p.throws AS throws,
        s.season AS season,
        s.classification AS classification,
        s.level AS level,
        s.hit_stats AS hit_stats,
        s.pitch_stats AS pitch_stats,
        s.roster_status AS roster_status,
        s.role AS role,
        s.role_type AS role_type,
        s.mlb_org AS mlb_org,
        s.is_mlb40man AS is_mlb40man,
        s.is_injured AS is_injured,
        s.is_starter AS is_starter,
        s.is_bench AS is_bench,
        s.injury_description AS injury_description
    FROM ulmg_playerstatseason s
    JOIN ulmg_player p ON p.id = s.player_id
    WHERE s.is_career IS NOT TRUE
      AND (
            TRIM(p.mlbam_id) = ANY(%s)
         OR TRIM(p.fg_id) = ANY(%s)
      )
    ORDER BY s.season NULLS LAST, s.id
"""


def clean_id(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def as_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except ValueError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def pick(blob, *keys):
    for key in keys:
        if key in blob and blob[key] not in (None, ""):
            return blob[key]
    return None


def as_percent(value):
    """FanGraphs stores rates as fractions. NPL displays them as percents."""
    number = utils.to_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        return round(number * 100, 3)
    return round(number, 3)


def stat_type(classification):
    text = (classification or "").lower()
    if text.startswith("1-") or text in {"mlb", "majors"}:
        return "majors"
    if "npb" in text:
        return "npb"
    if "kbo" in text:
        return "kbo"
    if "college" in text or "ncaa" in text:
        return "college"
    return "minors"


def level_label(classification, row_level, blob):
    raw = row_level or pick(blob, "level", "aLevel", "alevel")
    if raw:
        return str(raw).strip()
    kind = stat_type(classification)
    if kind == "majors":
        return "MLB"
    if kind == "npb":
        return "NPB"
    if kind == "kbo":
        return "KBO"
    if kind == "college":
        return "NCAA"
    return None


def roster_status_for(row):
    status = (row.get("roster_status") or "").strip()
    if status:
        return status
    level = (row.get("level") or "").strip().upper()
    if level == "MLB":
        return "MLB"
    if level in MINORS_LEVELS:
        return "MINORS"
    if level in ROOKIE_LEVELS:
        return "ROOKIE"
    return None


def _whole(value):
    return utils.to_int(value, default=0) or 0


def _optional_count(value):
    if value in (None, ""):
        return None
    return utils.to_int(value, default=0) or 0


def _keep(payload):
    """Drop missing rates. Counting stats stay, including zero."""
    return {key: value for key, value in payload.items() if value is not None}


def _rate(value):
    return utils.to_float(value, default=None)


def hitting_line(row):
    blob = as_json(row.get("hit_stats"))
    if not blob:
        return None
    plate_appearances = _whole(pick(blob, "pa", "PA", "plate_appearances"))
    if plate_appearances < 1:
        return None
    year = row.get("season")
    if not year:
        return None
    kind = stat_type(row.get("classification"))
    return _keep({
        "year": int(year),
        "type": kind,
        "level": level_label(row.get("classification"), row.get("level"), blob),
        "side": "hit",
        "slug": f"{int(year)}_{kind}_hit",
        "plate_appearances": plate_appearances,
        "ab": _whole(pick(blob, "ab", "AB")),
        "hits": _whole(pick(blob, "h", "H")),
        "2b": _whole(pick(blob, "2b", "2B")),
        "3b": _whole(pick(blob, "3b", "3B")),
        "hr": _whole(pick(blob, "hr", "HR")),
        "sb": _whole(pick(blob, "sb", "SB")),
        "runs": _whole(pick(blob, "r", "R")),
        "rbi": _whole(pick(blob, "rbi", "RBI")),
        "wrc_plus": _optional_count(pick(blob, "wrc_plus", "wRC+", "wrc+")),
        "avg": _rate(pick(blob, "avg", "AVG")),
        "xavg": _rate(pick(blob, "xavg", "xAVG")),
        "obp": _rate(pick(blob, "obp", "OBP")),
        "slg": _rate(pick(blob, "slg", "SLG")),
        "xslg": _rate(pick(blob, "xslg", "xSLG")),
        "babip": _rate(pick(blob, "babip", "BABIP")),
        "iso": _rate(pick(blob, "iso", "ISO")),
        "k_pct": as_percent(pick(blob, "k_pct", "K%")),
        "bb_pct": as_percent(pick(blob, "bb_pct", "BB%")),
        "xwoba": _rate(pick(blob, "xwoba", "xwOBA")),
        "woba": _rate(pick(blob, "woba", "wOBA")),
    })


def pitching_line(row):
    blob = as_json(row.get("pitch_stats"))
    if not blob:
        return None
    games = _whole(pick(blob, "g", "G"))
    innings = _rate(pick(blob, "ip", "IP")) or 0
    if games < 1 and innings <= 0:
        return None
    year = row.get("season")
    if not year:
        return None
    kind = stat_type(row.get("classification"))
    return _keep({
        "year": int(year),
        "type": kind,
        "level": level_label(row.get("classification"), row.get("level"), blob),
        "side": "pitch",
        "slug": f"{int(year)}_{kind}_pitch",
        "g": games,
        "gs": _whole(pick(blob, "gs", "GS")),
        "k": _whole(pick(blob, "so", "SO", "k")),
        "bb": _whole(pick(blob, "bb", "BB")),
        "ha": _whole(pick(blob, "h", "H")),
        "hra": _whole(pick(blob, "hr", "HR")),
        "ip": innings,
        "k_9": _rate(pick(blob, "k_9", "K/9")),
        "bb_9": _rate(pick(blob, "bb_9", "BB/9")),
        "hr_9": _rate(pick(blob, "hr_9", "HR/9")),
        "lob_pct": as_percent(pick(blob, "lob_pct", "LOB%")),
        "gb_pct": as_percent(pick(blob, "gb_pct", "GB%")),
        "hr_fb": _rate(pick(blob, "hr_fb", "HR/FB")),
        "era": _rate(pick(blob, "era", "ERA")),
        "fip": _rate(pick(blob, "fip", "FIP")),
        "xfip": _rate(pick(blob, "xfip", "xFIP")),
        "siera": _rate(pick(blob, "siera", "SIERA")),
        "xERA": _rate(pick(blob, "xera", "xERA")),
        "sp_stuff": _rate(pick(blob, "sp_stuff")),
        "sp_location": _rate(pick(blob, "sp_location")),
        "sp_pitching": _rate(pick(blob, "sp_pitching")),
        "er": _rate(pick(blob, "er", "ER")),
        "k_9+": _optional_count(pick(blob, "k_9_plus", "K/9+")),
        "bb_9+": _optional_count(pick(blob, "bb_9_plus", "BB/9+")),
        "era-": _optional_count(pick(blob, "era_minus", "ERA-")),
        "fip-": _optional_count(pick(blob, "fip_minus", "FIP-")),
        "xfip-": _optional_count(pick(blob, "xfip_minus", "xFIP-")),
    })


def stat_lines(rows):
    lines = {}
    for row in rows:
        for builder in (hitting_line, pitching_line):
            line = builder(row)
            if line:
                lines[line["slug"]] = line
    return lines


def current_status_row(rows):
    candidates = []
    for row in rows:
        if roster_status_for(row) or (row.get("level") or "").strip() or (row.get("role") or "").strip():
            candidates.append(row)
    if not candidates:
        return None

    def sort_key(row):
        season = row.get("season") or 0
        return (
            int(season),
            1 if (row.get("roster_status") or "").strip() else 0,
            1 if (row.get("level") or "").strip() else 0,
        )

    return max(candidates, key=sort_key)


def _role_flags(row):
    role_type = (row.get("role_type") or "").lower()
    role = (row.get("role") or "").lower()
    status = (row.get("roster_status") or "").upper()
    return {
        "fg_is_starter": bool(row.get("is_starter")) or role_type in {"mlb-sp", "mlb-sl"} or role in {"sp", "starter", "rotation"},
        "fg_is_bench": bool(row.get("is_bench")) or role_type == "mlb-bn" or role == "bench",
        "fg_is_injured": bool(row.get("is_injured")) or status.startswith("IL"),
        "fg_is_mlb40man": bool(row.get("is_mlb40man")),
    }


SEASON_UPDATE_FIELDS = (
    "level",
    "hit_stats",
    "pitch_stats",
    "minors",
    "is_mlb",
    "is_starter",
    "is_bench",
    "is_injured",
    "injury_description",
    "role",
    "role_type",
    "roster_status",
    "mlb_org",
    "is_mlb40man",
)


def _text(value, limit=255):
    return str(value or "").strip()[:limit]


def json_or_none(value):
    blob = as_json(value)
    return blob or None


def season_from_row(player, row):
    """Build an unsaved PlayerStatSeason. Returns None when the year is missing."""
    if not row.get("season"):
        return None
    classification = _text(row.get("classification"))
    level = _text(row.get("level"))
    flags = _role_flags(row)
    roster_status = roster_status_for(row) or ""
    return models.PlayerStatSeason(
        player=player,
        season=int(row["season"]),
        is_career=False,
        classification=classification,
        level=level,
        hit_stats=json_or_none(row.get("hit_stats")),
        pitch_stats=json_or_none(row.get("pitch_stats")),
        minors=classification.startswith("2-") or roster_status == "MINORS",
        is_mlb=classification.startswith("1-") or level.upper() == "MLB",
        injury_description=_text(row.get("injury_description")),
        role=_text(row.get("role")),
        role_type=_text(row.get("role_type")),
        roster_status=roster_status,
        mlb_org=_text(row.get("mlb_org") or row.get("current_mlb_org")),
        is_starter=flags["fg_is_starter"],
        is_bench=flags["fg_is_bench"],
        is_injured=flags["fg_is_injured"],
        is_mlb40man=flags["fg_is_mlb40man"],
    )


def apply_player(player, rows, fg_ids_in_use):
    """Copy the current roster line onto the player. Season stats are stored separately."""
    changed = []

    lines = stat_lines(rows)
    if lines and any(line["type"] == "majors" for line in lines.values()) and player.has_appeared_in_majors is not True:
        player.has_appeared_in_majors = True
        changed.append("has_appeared_in_majors")

    status = current_status_row(rows)
    if status:
        roster_status = roster_status_for(status)
        if roster_status and roster_status != player.roster_status:
            player.roster_status = roster_status
            changed.append("roster_status")

        org = (status.get("mlb_org") or status.get("current_mlb_org") or "").strip()
        if org and org != (player.mlb_org or ""):
            player.mlb_org = org
            changed.append("mlb_org")

        level = (status.get("level") or "").strip()
        role = (status.get("role") or "").strip()
        fg_role = level or role
        if fg_role and fg_role != (player.fg_role or ""):
            player.fg_role = fg_role
            changed.append("fg_role")

        role_type = (status.get("role_type") or "").strip()
        if role_type and role_type != (player.fg_role_type or ""):
            player.fg_role_type = role_type
            changed.append("fg_role_type")

        injury = (status.get("injury_description") or "").strip()
        if injury and injury != (player.fg_injury_description or ""):
            player.fg_injury_description = injury
            changed.append("fg_injury_description")

        for field, value in _role_flags(status).items():
            if getattr(player, field) != value:
                setattr(player, field, value)
                changed.append(field)

    fg_id = clean_id(rows[0].get("fg_id") if rows else None)
    if fg_id and not player.fg_id and fg_id not in fg_ids_in_use:
        player.fg_id = fg_id
        fg_ids_in_use.add(fg_id)
        changed.append("fg_id")

    for field in ("bats", "throws"):
        incoming = (rows[0].get(field) or "").strip() if rows else ""
        if incoming and not getattr(player, field):
            setattr(player, field, incoming[:3])
            changed.append(field)

    return changed


def match_player(row, by_mlb, by_fg):
    mlb_id = clean_id(row.get("mlbam_id"))
    if mlb_id and mlb_id in by_mlb:
        return by_mlb[mlb_id]
    fg_id = clean_id(row.get("fg_id"))
    if fg_id and fg_id in by_fg:
        return by_fg[fg_id]
    return None


def import_rows(rows, dry_run=False):
    """Apply fetched ULMG rows to NPL. Returns a count summary."""
    summary = {
        "ulmg_players": 0,
        "matched": 0,
        "updated": 0,
        "stat_lines": 0,
        "status": 0,
        "skipped": 0,
        "seasons_created": 0,
        "seasons_refreshed": 0,
    }
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get("player_id"), []).append(row)
    summary["ulmg_players"] = len(grouped)

    players = list(models.Player.objects.all())
    by_mlb = {clean_id(player.mlb_id): player for player in players if clean_id(player.mlb_id)}
    by_fg = {}
    fg_ids_in_use = set()
    for player in players:
        fg_id = clean_id(player.fg_id)
        if fg_id and fg_id not in by_fg:
            by_fg[fg_id] = player
            fg_ids_in_use.add(fg_id)

    pending = []
    update_fields = set()
    seasons = {}
    for group in grouped.values():
        player = match_player(group[0], by_mlb, by_fg)
        if player is None:
            summary["skipped"] += 1
            continue
        summary["matched"] += 1
        summary["stat_lines"] += len(stat_lines(group))
        if current_status_row(group):
            summary["status"] += 1
        for row in group:
            season = season_from_row(player, row)
            if season is None:
                continue
            seasons[(season.player_id, season.season, season.classification, season.is_career)] = season
        changed = apply_player(player, group, fg_ids_in_use)
        if not changed:
            continue
        summary["updated"] += 1
        update_fields.update(changed)
        if player not in pending:
            pending.append(player)

    existing = set()
    player_ids = {key[0] for key in seasons}
    if player_ids:
        existing = set(
            models.PlayerStatSeason.objects.filter(player_id__in=player_ids).values_list(
                "player_id", "season", "classification", "is_career"
            )
        )
    summary["seasons_created"] = sum(1 for key in seasons if key not in existing)
    summary["seasons_refreshed"] = len(seasons) - summary["seasons_created"]

    if not dry_run:
        if seasons:
            models.PlayerStatSeason.objects.bulk_create(
                list(seasons.values()),
                batch_size=500,
                update_conflicts=True,
                unique_fields=["player", "season", "classification", "is_career"],
                update_fields=list(SEASON_UPDATE_FIELDS),
            )
        if pending:
            models.Player.objects.bulk_update(pending, sorted(update_fields), batch_size=200)
    return summary


def fetch_rows(database_url, years=None):
    """Read ULMG season rows for players NPL can match on MLB id or FanGraphs id."""
    import dj_database_url

    identities = list(models.Player.objects.values_list("mlb_id", "fg_id"))
    mlb_ids = sorted({clean_id(mlb_id) for mlb_id, _fg_id in identities if clean_id(mlb_id)})
    fg_ids = sorted({clean_id(fg_id) for _mlb_id, fg_id in identities if clean_id(fg_id)})
    if not mlb_ids and not fg_ids:
        return []

    config = dj_database_url.parse(database_url, conn_max_age=0)
    options = dict(config.get("OPTIONS") or {})
    options["connect_timeout"] = 15
    options["options"] = "-c statement_timeout=180000"
    config["OPTIONS"] = options
    from django.conf import settings as django_settings

    config["ATOMIC_REQUESTS"] = False
    config["AUTOCOMMIT"] = True
    config["TIME_ZONE"] = django_settings.TIME_ZONE
    config["CONN_HEALTH_CHECKS"] = False
    connections.databases["ulmg"] = config

    sql = FETCH_SQL
    params = [mlb_ids or [""], fg_ids or [""]]
    if years:
        sql = sql.replace(
            "ORDER BY",
            "AND s.season = ANY(%s)\n    ORDER BY",
            1,
        )
        params.append([int(year) for year in years])

    try:
        with connections["ulmg"].cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connections["ulmg"].close()


def database_url():
    return os.environ.get("ULMG_DATABASE_URL") or ""
