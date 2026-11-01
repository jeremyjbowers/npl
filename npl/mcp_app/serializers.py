"""JSON shapes for the NPL MCP read API."""

from django.db.models import Prefetch

from npl import models, utils


def stat_prefetch(lookup="stat_seasons"):
    return Prefetch(
        lookup,
        queryset=models.PlayerStatSeason.objects.filter(is_career=False).order_by(
            "-season", "classification"
        ),
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


def _latest_stat(player):
    seasons = getattr(player, "mcp_stat_seasons", None)
    if seasons is None:
        seasons = list(
            player.stat_seasons.filter(is_career=False).order_by("-season", "classification")[:1]
        )
    if not seasons:
        return None
    season = seasons[0]
    return {
        "season": season.season,
        "classification": season.classification,
        "level": season.level,
        "roster_status": season.roster_status,
        "mlb_org": season.mlb_org,
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
        "contract": _contract_brief(player),
    }
