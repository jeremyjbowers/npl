"""The public season: the schedule, the standings, and the sim leaders."""

from django.db.models import Q

from npl import models, utils
from npl.game_models import NPL_SIM


HITTING = (
    ("avg", "Batting average", "rate3", True, False),
    ("obp", "On-base percentage", "rate3", True, False),
    ("slg", "Slugging", "rate3", True, False),
    ("ops", "OPS", "rate3", True, False),
    ("hr", "Home runs", "count", False, False),
    ("rbi", "Runs batted in", "count", False, False),
    ("r", "Runs", "count", False, False),
    ("h", "Hits", "count", False, False),
    ("bb", "Walks", "count", False, False),
    ("k", "Strikeouts", "count", False, False),
)
PITCHING = (
    ("era", "ERA", "rate2", True, True),
    ("whip", "WHIP", "rate2", True, True),
    ("k_9", "Strikeouts per 9", "rate2", True, False),
    ("bb_9", "Walks per 9", "rate2", True, True),
    ("w", "Wins", "count", False, False),
    ("sv", "Saves", "count", False, False),
    ("k", "Strikeouts", "count", False, False),
    ("ip", "Innings", "ip", False, False),
)


def calendar_year():
    """The season the public pages open on. November already belongs to next year."""
    return utils.get_current_season()


def season_for(year):
    return models.Season.objects.filter(year=year).order_by("-is_current", "-id").first()


def schedule_page(year):
    season = season_for(year)
    weeks = _weeks(season)
    return {
        "season": season,
        "year": year,
        "weeks": weeks,
        "divisions": _standings(season, _clubs(weeks)),
    }


def team_schedule(team, year):
    season = season_for(year)
    rows = []
    if season is None:
        return {"season": None, "year": year, "rows": rows, "record": None}
    series = (
        models.WeekSeries.objects.filter(week__season=season)
        .filter(Q(home_team=team) | Q(road_team=team))
        .select_related("week", "home_team", "road_team")
        .prefetch_related("results")
        .order_by("week__number", "id")
    )
    for item in series:
        home = item.home_team_id == team.id
        opponent = item.road_team if home else item.home_team
        games = []
        wins = losses = 0
        for game in item.results.all():
            ours = game.home_score if home else game.road_score
            theirs = game.road_score if home else game.home_score
            if game.is_played:
                if ours > theirs:
                    wins += 1
                elif ours < theirs:
                    losses += 1
            games.append({"game": game, "ours": ours, "theirs": theirs, "played": game.is_played})
        rows.append({
            "week": item.week,
            "series": item,
            "opponent": opponent,
            "home": home,
            "games": games,
            "wins": wins,
            "losses": losses,
        })
    return {"season": season, "year": year, "rows": rows, "record": _record(team, season)}


def team_stats(team, year):
    season = season_for(year)
    lines = models.PlayerStatSeason.objects.filter(
        team=team, season=year, classification=NPL_SIM, is_career=False
    ).select_related("player")
    hitters = []
    pitchers = []
    for line in lines:
        if line.hit_stats and int(line.hit_stats.get("pa") or 0) > 0:
            stats = dict(line.hit_stats)
            stats["doubles"] = stats.get("2b") or 0
            stats["triples"] = stats.get("3b") or 0
            hitters.append({"player": line.player, "stats": stats})
        pitching = _pitching(line.pitch_stats)
        if pitching and (pitching["outs"] > 0 or pitching["g"] > 0):
            pitchers.append({"player": line.player, "stats": pitching})
    hitters.sort(key=lambda row: (-int(row["stats"].get("pa") or 0), row["player"].name or ""))
    pitchers.sort(key=lambda row: (-int(row["stats"].get("outs") or 0), row["player"].name or ""))
    return {
        "season": season,
        "year": year,
        "hitters": hitters,
        "pitchers": pitchers,
        "record": _record(team, season) if season else None,
    }


def leaders(year):
    """Top ten in each category we store from the simulated season."""
    season = season_for(year)
    games = 0
    if season is not None:
        for record in models.SimTeamSeason.objects.filter(season=season):
            games = max(games, record.wins + record.losses)
    plate_min = max(1, round(3.1 * games)) if games else 1
    out_min = max(3, games * 3) if games else 3
    rows = list(
        models.PlayerStatSeason.objects.filter(season=year, classification=NPL_SIM, is_career=False)
        .select_related("player", "team")
    )
    return {
        "season": season,
        "year": year,
        "games": games,
        "hitting": _boards(rows, HITTING, "hit_stats", plate_min, "plate appearances"),
        "pitching": _boards(rows, PITCHING, "pitch_stats", out_min, "innings"),
    }


def _weeks(season):
    if season is None:
        return []
    series = (
        models.WeekSeries.objects.filter(week__season=season)
        .select_related("week", "home_team", "road_team")
        .prefetch_related("results")
        .order_by("week__number", "home_team__abbreviation")
    )
    grouped = {}
    for item in series:
        road_wins, home_wins = _series_wins(item)
        item.road_wins = road_wins
        item.home_wins = home_wins
        item.played = road_wins + home_wins
        grouped.setdefault(item.week_id, {"week": item.week, "series": []})
        grouped[item.week_id]["series"].append(item)
    return [grouped[key] for key in sorted(grouped, key=lambda week_id: grouped[week_id]["week"].number)]


def _series_wins(series):
    road_wins = home_wins = 0
    for game in series.results.all():
        if not game.is_played:
            continue
        if game.road_score > game.home_score:
            road_wins += 1
        elif game.home_score > game.road_score:
            home_wins += 1
    return road_wins, home_wins


def _clubs(weeks):
    found = {}
    for group in weeks:
        for series in group["series"]:
            found[series.road_team_id] = series.road_team
            found[series.home_team_id] = series.home_team
    return found


def _standings(season, clubs):
    if season is None or not clubs:
        return []
    records = {
        row.team_id: row
        for row in models.SimTeamSeason.objects.filter(season=season, team_id__in=clubs)
    }
    grouped = {}
    for team in clubs.values():
        record = records.get(team.pk)
        grouped.setdefault(utils.division_label(team), []).append({
            "team": team,
            "wins": record.wins if record else 0,
            "losses": record.losses if record else 0,
            "runs_scored": record.runs_scored if record else 0,
            "runs_allowed": record.runs_allowed if record else 0,
            "place": record.division_place if record else None,
        })
    divisions = []
    for name in sorted(grouped):
        rows = grouped[name]
        rows.sort(key=lambda row: (
            row["place"] is None,
            row["place"] or 0,
            -row["wins"],
            row["losses"],
            row["team"].abbreviation or "",
        ))
        leader = rows[0]
        for row in rows:
            behind = ((leader["wins"] - row["wins"]) + (row["losses"] - leader["losses"])) / 2
            row["behind"] = "—" if behind == 0 else f"{behind:g}"
            row["diff"] = row["runs_scored"] - row["runs_allowed"]
        divisions.append({"name": name, "rows": rows})
    return divisions


def _record(team, season):
    if season is None:
        return None
    return models.SimTeamSeason.objects.filter(team=team, season=season).first()


def _boards(lines, categories, side, minimum, minimum_label):
    prepared = []
    for line in lines:
        stats = _hitting(line.hit_stats) if side == "hit_stats" else _pitching(line.pitch_stats)
        if not stats:
            continue
        sample = int(stats.get("pa") or 0) if side == "hit_stats" else int(stats.get("outs") or 0)
        prepared.append({"player": line.player, "team": line.team, "stats": stats, "sample": sample})
    boards = []
    for key, title, kind, qualified, lower in categories:
        pool = prepared
        if qualified:
            pool = [row for row in pool if row["sample"] >= minimum]
        ranked = []
        for row in pool:
            value = row["stats"].get(key)
            if value is None:
                continue
            if kind == "count" and not value:
                continue
            ranked.append((value, row))
        ranked.sort(key=lambda item: (item[0] if lower else -item[0], item[1]["player"].name or ""))
        boards.append({
            "title": title,
            "qualified": qualified,
            "minimum": _minimum_text(minimum, minimum_label) if qualified else "",
            "rows": [
                {
                    "rank": index,
                    "player": row["player"],
                    "team": row["team"],
                    "value": _format(value, kind, row["stats"]),
                    "sample": _sample(row, side),
                }
                for index, (value, row) in enumerate(ranked[:10], start=1)
            ],
        })
    return boards


def _minimum_text(minimum, label):
    if label == "innings":
        return f"At least {minimum // 3}.{minimum % 3} innings"
    return f"At least {minimum} {label}"


def _hitting(stats):
    if not stats or int(stats.get("pa") or 0) < 1:
        return None
    stats = dict(stats)
    obp, slg = stats.get("obp"), stats.get("slg")
    stats["ops"] = None if obp is None or slg is None else obp + slg
    return stats


def _pitching(stats):
    if not stats:
        return None
    outs = int(stats.get("outs") or 0)
    games = int(stats.get("g") or 0)
    if outs <= 0 and games <= 0:
        return None
    stats = dict(stats)
    stats["outs"] = outs
    hits = int(stats.get("h") or 0)
    walks = int(stats.get("bb") or 0)
    stats["whip"] = None if outs <= 0 else (hits + walks) * 3 / outs
    stats["ip_display"] = f"{outs // 3}.{outs % 3}"
    return stats


def _format(value, kind, stats):
    if kind == "ip":
        return stats.get("ip_display") or value
    if kind == "count":
        return f"{int(value)}"
    if kind == "rate2":
        return f"{float(value):.2f}"
    text = f"{float(value):.3f}"
    return text[1:] if text.startswith("0") else text


def _sample(row, side):
    if side == "hit_stats":
        return f"{int(row['stats'].get('pa') or 0)} PA"
    return f"{row['stats'].get('ip_display')} IP"
