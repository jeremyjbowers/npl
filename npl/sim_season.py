"""Sim player lines and standings, summed from the box scores.

Player lines use the classification ``npl``. MLB lines use every other
classification. ``SimTeamSeason`` is the standings. ``TeamSeason`` is the
franchise sheet and is left alone.
"""

from django.db import transaction

from npl import models
from npl.game_models import NPL_SIM


BATTING_KEYS = ("pa", "ab", "r", "h", "hr", "2b", "3b", "rbi", "bb", "k", "hbp", "sf")
PITCHING_KEYS = ("outs", "h", "r", "er", "bb", "k", "hr", "bf", "w", "l", "sv", "g", "gs")


def rebuild_sim_season(season):
    """Rewrite the season's sim lines and standings from the played games."""
    totals = _totals(season)
    with transaction.atomic():
        written, deleted = _write_players(season, totals)
        records, removed = _write_teams(season, totals)
    return {"players": written, "players_deleted": deleted, "teams": records, "teams_deleted": removed}


def purge_sim(season, week_number=None):
    """
    Clear simulated games. A week clears that week and rebuilds the season
    from the games that remain. A season clears every simulated game, the
    ``npl`` player lines, and the sim standings.
    """
    games = models.WeekGame.objects.filter(series__week__season=season)
    if week_number is not None:
        games = games.filter(series__week__number=week_number)
    with transaction.atomic():
        cleared = games.update(home_score=None, road_score=None, box_score=None)
        if week_number is None:
            players, _ = models.PlayerStatSeason.objects.filter(season=season.year, classification=NPL_SIM).delete()
            teams, _ = models.SimTeamSeason.objects.filter(season=season).delete()
            return {"games": cleared, "players": players, "teams": teams}
    rebuilt = rebuild_sim_season(season)
    return {"games": cleared, **rebuilt}


def _totals(season):
    batting = {}
    pitching = {}
    teams = {}
    games = (
        models.WeekGame.objects.filter(series__week__season=season, home_score__isnull=False, road_score__isnull=False)
        .select_related("series__home_team", "series__road_team")
    )
    for game in games:
        box = game.box_score or {}
        sides = (
            ("away", game.series.road_team_id, game.road_score, game.home_score),
            ("home", game.series.home_team_id, game.home_score, game.road_score),
        )
        for side, team_id, scored, allowed in sides:
            block = box.get(side) or {}
            for line in block.get("batting") or []:
                row = _player(batting, line.get("player_id"), BATTING_KEYS)
                if row is None:
                    continue
                row["g"] += 1
                for key in BATTING_KEYS:
                    row[key] += int(line.get(key) or 0)
            for index, line in enumerate(block.get("pitching") or []):
                row = _player(pitching, line.get("player_id"), PITCHING_KEYS)
                if row is None:
                    continue
                row["g"] += 1
                if index == 0:
                    row["gs"] += 1
                for key in ("outs", "h", "r", "er", "bb", "k", "hr", "bf"):
                    row[key] += int(line.get(key) or 0)
            record = teams.setdefault(team_id, {"wins": 0, "losses": 0, "runs_scored": 0, "runs_allowed": 0})
            record["runs_scored"] += int(scored or 0)
            record["runs_allowed"] += int(allowed or 0)
            if scored > allowed:
                record["wins"] += 1
            elif scored < allowed:
                record["losses"] += 1
        for key, label in (("win_id", "w"), ("loss_id", "l"), ("save_id", "sv")):
            player_id = box.get(key)
            row = _player(pitching, player_id, PITCHING_KEYS)
            if row is not None:
                row[label] += 1
    return {"batting": batting, "pitching": pitching, "teams": teams}


def _player(store, player_id, keys):
    if not player_id:
        return None
    row = store.get(player_id)
    if row is None:
        row = {key: 0 for key in keys}
        row["g"] = 0
        store[player_id] = row
    return row


def _write_players(season, totals):
    played = set(totals["batting"]) | set(totals["pitching"])
    existing = models.PlayerStatSeason.objects.filter(season=season.year, classification=NPL_SIM, is_career=False)
    deleted, _ = existing.exclude(player_id__in=played).delete()
    known = set(models.Player.objects.filter(mlb_id__in=played).values_list("mlb_id", flat=True))
    written = 0
    for player_id in played & known:
        models.PlayerStatSeason.objects.update_or_create(
            player_id=player_id,
            season=season.year,
            classification=NPL_SIM,
            is_career=False,
            defaults={
                "level": "NPL",
                "is_mlb": False,
                "minors": False,
                "hit_stats": _hit_stats(totals["batting"].get(player_id)),
                "pitch_stats": _pitch_stats(totals["pitching"].get(player_id)),
            },
        )
        written += 1
    return written, deleted


def _write_teams(season, totals):
    existing = models.SimTeamSeason.objects.filter(season=season)
    deleted, _ = existing.exclude(team_id__in=totals["teams"]).delete()
    written = 0
    rows = []
    for team_id, record in totals["teams"].items():
        row, _ = models.SimTeamSeason.objects.update_or_create(
            team_id=team_id,
            season=season,
            defaults=record,
        )
        rows.append(row)
        written += 1
    _places(rows)
    return written, deleted


def _places(rows):
    divisions = dict(
        models.Team.objects.filter(pk__in=[row.team_id for row in rows]).values_list("pk", "division_id")
    )
    groups = {}
    for row in rows:
        groups.setdefault(divisions.get(row.team_id), []).append(row)
    for group in groups.values():
        group.sort(key=lambda row: (-row.wins, row.losses, -(row.runs_scored - row.runs_allowed), row.team_id))
        for place, row in enumerate(group, start=1):
            if row.division_place != place:
                row.division_place = place
                row.save(update_fields=["division_place", "last_modified"])


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return numerator / denominator


def _hit_stats(row):
    if not row:
        return None
    singles = row["h"] - row["hr"] - row["2b"] - row["3b"]
    at_bats = row["ab"]
    stats = dict(row)
    stats["plate_appearances"] = row["pa"]
    stats["so"] = row["k"]
    stats["avg"] = _ratio(row["h"], at_bats)
    stats["obp"] = _ratio(row["h"] + row["bb"] + row["hbp"], at_bats + row["bb"] + row["hbp"] + row["sf"])
    total_bases = singles + 2 * row["2b"] + 3 * row["3b"] + 4 * row["hr"]
    stats["slg"] = _ratio(total_bases, at_bats)
    balls = at_bats - row["k"] - row["hr"] + row["sf"]
    stats["babip"] = _ratio(row["h"] - row["hr"], balls)
    stats["k_pct"] = None if not row["pa"] else round(100.0 * row["k"] / row["pa"], 1)
    stats["bb_pct"] = None if not row["pa"] else round(100.0 * row["bb"] / row["pa"], 1)
    return stats


def _pitch_stats(row):
    if not row:
        return None
    stats = {key: value for key, value in row.items() if key != "outs"}
    outs = row["outs"]
    stats["outs"] = outs
    stats["ip"] = float(f"{outs // 3}.{outs % 3}")
    stats["so"] = row["k"]
    stats["era"] = _ratio(27 * row["er"], outs)
    stats["k_9"] = _ratio(27 * row["k"], outs)
    stats["bb_9"] = _ratio(27 * row["bb"], outs)
    stats["hr_9"] = _ratio(27 * row["hr"], outs)
    stats["h_9"] = _ratio(27 * row["h"], outs)
    return stats
