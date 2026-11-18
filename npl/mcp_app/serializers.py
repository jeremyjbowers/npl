"""JSON shapes for the NPL MCP read API."""

from django.db.models import Prefetch

from npl import models, utils


def stat_prefetch(lookup="stat_seasons"):
    return Prefetch(
        lookup,
        queryset=models.PlayerStatSeason.objects.filter(is_career=False)
        .select_related("team")
        .order_by("-season", "classification"),
        to_attr="mcp_stat_seasons",
    )


def contract_prefetch():
    return Prefetch(
        "contract_set",
        queryset=models.Contract.objects.prefetch_related("contractyear_set"),
    )


def team_brief(team):
    if team is None:
        return None
    return {
        "id": team.id,
        "abbreviation": team.abbreviation,
        "short_name": team.short_name,
        "full_name": team.full_name,
        "division": utils.division_label(team),
        "mlb_payroll": team.mlb_payroll,
        "contract_salary": team.contract_salary,
        "carried_salary": team.carried_salary,
        "cap_space": team.cap_space,
        "luxury_cap_space": team.luxury_cap_space,
        "cash": team.cash,
        "ifa": team.ifa,
        "can_transact": team.can_transact,
    }


_WAR_KEYS = ("war", "WAR", "fWAR", "fwar", "bWAR", "bwar", "WAR_bat", "war_bat", "WAR_pit", "war_pit")

MLB_WAR_NOTE = "Full MLB season, not split by NPL club."


def sheet_label(value):
    text = (value or "").strip()
    if text in {"", "-", "—"}:
        return None
    return text


def club_name(team, raw=None):
    """The name the site shows: current short name, then the sheet's own label."""
    if team is not None:
        return team.short_name or team.full_name or team.abbreviation or sheet_label(raw)
    return sheet_label(raw)


def club_token(team, raw=None):
    if team is not None and team.abbreviation:
        return team.abbreviation
    return club_name(team, raw)


def club_dict(team, raw=None):
    if team is None and sheet_label(raw) is None:
        return None
    return {
        "abbreviation": team.abbreviation if team is not None else None,
        "short_name": team.short_name if team is not None else None,
        "full_name": team.full_name if team is not None else None,
        "name": club_name(team, raw),
        "sheet_name": sheet_label(raw),
    }


def _seasons(player):
    seasons = getattr(player, "mcp_stat_seasons", None)
    if seasons is None:
        seasons = list(
            player.stat_seasons.filter(is_career=False)
            .select_related("team")
            .order_by("-season", "classification")
        )
    return seasons


def _number(value):
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _blob_war(blob):
    if not isinstance(blob, dict):
        return None
    for key in _WAR_KEYS:
        found = _number(blob.get(key))
        if found is not None:
            return found
    return None


def season_war(season):
    """WAR stored on the stat line. A two-way season keeps both values when they differ."""
    values = [value for value in (_blob_war(season.hit_stats), _blob_war(season.pitch_stats)) if value is not None]
    if not values:
        return None
    if len(values) == 1 or abs(values[0] - values[1]) < 0.05:
        return values[0]
    return round(values[0] + values[1], 3)


def stat_scope(season):
    classification = (season.classification or "").strip()
    if season.team_id or classification.lower() == "npl":
        return "npl_club"
    level = (season.level or "").strip().upper()
    if season.is_mlb or level == "MLB" or classification.startswith("1-"):
        return "mlb_season"
    return "other"


def war_record(player):
    """The newest full-season MLB WAR. Club-split sim lines do not replace it."""
    seasons = _seasons(player)
    mlb = [season for season in seasons if stat_scope(season) == "mlb_season"]
    for season in sorted(mlb, key=lambda item: item.season, reverse=True):
        value = season_war(season)
        if value is not None:
            return value, season
    for season in sorted(seasons, key=lambda item: item.season, reverse=True):
        value = season_war(season)
        if value is not None:
            return value, season
    return None, None


def npl_lines(player):
    """Sim stats already split by the NPL club that used the player."""
    lines = []
    for season in _seasons(player):
        if stat_scope(season) != "npl_club":
            continue
        team = getattr(season, "team", None)
        lines.append(
            {
                "season": season.season,
                "team": team.abbreviation if team else None,
                "team_name": team.short_name if team else None,
                "classification": season.classification,
                "hit": season.hit_stats,
                "pitch": season.pitch_stats,
                "war": season_war(season),
            }
        )
    return lines


def _latest_stat(player):
    seasons = _seasons(player)
    if not seasons:
        return None
    season = seasons[0]
    return {
        "season": season.season,
        "classification": season.classification,
        "level": season.level,
        "roster_status": season.roster_status,
        "mlb_org": season.mlb_org,
        "team": season.team.abbreviation if season.team_id and getattr(season, "team", None) else None,
        "team_name": season.team.short_name if season.team_id and getattr(season, "team", None) else None,
        "scope": stat_scope(season),
        "hit": season.hit_stats,
        "pitch": season.pitch_stats,
    }


def _contract_brief(player):
    cache = getattr(player, "_prefetched_objects_cache", None) or {}
    if "contract_set" not in cache:
        return None
    contracts = list(player.contract_set.all())
    if not contracts:
        return None
    contract = contracts[0]
    years = [
        {"year": item.year, "amount": item.amount, "salary_class": item.salary_class}
        for item in contract.contractyear_set.all()
    ]
    return {
        "total_amount": contract.total_amount,
        "total_years": contract.total_years,
        "terms_pending": contract.terms_pending,
        "can_buyout": contract.can_buyout,
        "buyout_amount": contract.buyout_amount,
        "years": years,
    }


def player_brief(player):
    if player is None:
        return None
    team = getattr(player, "team", None)
    war, war_season = war_record(player)
    scope = stat_scope(war_season) if war_season is not None else None
    return {
        "mlb_id": player.mlb_id,
        "name": player.name,
        "position": player.position,
        "simple_position": player.simple_position,
        "level": player.player_level,
        "bats": player.bats,
        "throws": player.throws,
        "team": team.abbreviation if team else None,
        "team_short_name": team.short_name if team else None,
        "mlb_org": player.mlb_org,
        "is_owned": player.is_owned,
        "roster_40man": bool(player.roster_40man),
        "roster_30man": bool(player.roster_30man),
        "roster_85man": bool(player.roster_85man),
        "roster_7dayIL": bool(player.roster_7dayIL),
        "roster_56dayIL": bool(player.roster_56dayIL),
        "roster_eosIL": bool(player.roster_eosIL),
        "roster_restricted": bool(player.roster_restricted),
        "roster_tripleA": bool(player.roster_tripleA),
        "roster_tripleA_option": bool(player.roster_tripleA_option),
        "roster_doubleA": bool(player.roster_doubleA),
        "roster_singleA": bool(player.roster_singleA),
        "roster_outrighted": bool(player.roster_outrighted),
        "roster_foreign": bool(player.roster_foreign),
        "roster_retired": bool(player.roster_retired),
        "roster_nonroster": bool(player.roster_nonroster),
        "offseason_fa": bool(player.offseason_fa),
        "sta": player.sta,
        "mls_time": player.mls_time,
        "stats": _latest_stat(player),
        "war": war,
        "war_season": war_season.season if war_season is not None else None,
        "war_scope": scope if war is not None else None,
        "war_note": MLB_WAR_NOTE if scope == "mlb_season" and war is not None else None,
        "npl_lines": npl_lines(player),
        "contract": _contract_brief(player),
    }
