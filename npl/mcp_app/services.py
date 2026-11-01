"""Read-only lookups shared by the MCP JSON API and in-process tools."""

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from npl import models
from npl.mcp_app import serializers
from npl.rosters import build_sections, is_active_mlb
from npl.transactions.impact import (
    FORTY_LIMIT,
    RESERVE_LIMIT,
    counts_on_forty,
    counts_on_reserve,
    roster_roundup,
)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"y", "yes", "t", "true", "on", "1"}


def team_for_owner(owner):
    if owner is None:
        return None
    return (
        models.Team.objects.filter(owners=owner)
        .select_related("league", "division")
        .first()
    )


def resolve_team(abbreviation):
    key = (abbreviation or "").strip()
    if not key:
        raise models.Team.DoesNotExist
    team = (
        models.Team.objects.filter(abbreviation__iexact=key)
        .select_related("league", "division")
        .first()
    )
    if team is None:
        team = (
            models.Team.objects.filter(short_name__iexact=key)
            .select_related("league", "division")
            .first()
        )
    if team is None:
        raise models.Team.DoesNotExist
    return team


def require_team(owner, abbreviation=None):
    if abbreviation:
        return resolve_team(abbreviation)
    team = team_for_owner(owner)
    if team is None:
        raise models.Team.DoesNotExist
    return team


def get_season_context(owner=None):
    season = models.Season.current()
    team = team_for_owner(owner)
    year = season.year if season else getattr(settings, "LEAGUE_YEAR", None)
    phase = season.phase if season else models.Season.league_phase()
    return {
        "year": year,
        "phase": phase,
        "phase_label": dict(models.Season.PHASE_CHOICES).get(phase, phase),
        "league_min": season.league_min if season else None,
        "qo_salary": season.qo_salary if season else None,
        "salary_cap": season.salary_cap if season else None,
        "opening_day": season.opening_day.isoformat() if season and season.opening_day else None,
        "end_of_season": season.end_of_season.isoformat() if season and season.end_of_season else None,
        "forty_man_cap": FORTY_LIMIT,
        "reserve_cap": RESERVE_LIMIT,
        "my_team": serializers.team_brief(team),
        "my_owner": (
            {
                "name": owner.name,
                "email": owner.email or (owner.user.email if owner.user_id else ""),
            }
            if owner
            else None
        ),
    }


def list_teams():
    teams = models.Team.objects.select_related("league", "division").order_by(
        "league__name", "division__name", "abbreviation", "short_name"
    )
    return {"teams": [serializers.team_brief(team) for team in teams]}


def _roster_players(team):
    return list(
        models.Player.objects.filter(team=team)
        .select_related("team")
        .prefetch_related(serializers.stat_prefetch(), serializers.contract_prefetch())
    )


def get_team_roster(abbreviation=None, owner=None):
    team = require_team(owner, abbreviation)
    players = _roster_players(team)
    sections = []
    seen = set()
    for section in build_sections(players):
        briefs = [serializers.player_brief(player) for player in section["players"]]
        seen.update(item["mlb_id"] for item in briefs)
        sections.append({"key": section["key"], "title": section["title"], "players": briefs})
    unsectioned = [
        serializers.player_brief(player) for player in players if player.mlb_id not in seen
    ]
    return {
        "team": serializers.team_brief(team),
        "counts": {
            "total": len(players),
            "active_mlb": sum(1 for player in players if is_active_mlb(player)),
            "forty_man": sum(1 for player in players if counts_on_forty(player)),
            "reserve": sum(1 for player in players if counts_on_reserve(player)),
            "roster_30man": sum(1 for player in players if player.roster_30man),
        },
        "sections": sections,
        "unsectioned": unsectioned,
    }


def get_roster_compliance(abbreviation=None, owner=None):
    team = require_team(owner, abbreviation)
    players = models.Player.objects.filter(team=team).only(
        "mlb_id",
        "team_id",
        "roster_40man",
        "roster_30man",
        "roster_eosIL",
        "roster_foreign",
        "roster_retired",
    )
    members = list(players)
    forty = sum(1 for player in members if counts_on_forty(player))
    reserve = sum(1 for player in members if counts_on_reserve(player))
    warnings = []
    for row in roster_roundup():
        if row["team"].id == team.id:
            forty = row["forty"]
            reserve = row["reserve"]
            warnings = row["lines"]
            break
    return {
        "team": serializers.team_brief(team),
        "counts": {
            "forty_man": forty,
            "reserve": reserve,
            "roster_30man": sum(1 for player in members if player.roster_30man),
        },
        "limits": {
            "forty_man_cap": FORTY_LIMIT,
            "forty_man_ok": forty <= FORTY_LIMIT,
            "reserve_cap": RESERVE_LIMIT,
            "reserve_ok": reserve <= RESERVE_LIMIT,
        },
        "warnings": warnings,
    }


def search_players(
    *,
    name=None,
    position=None,
    owned=None,
    team=None,
    level=None,
    roster_40man=None,
    roster_30man=None,
    limit=100,
):
    limit = min(max(_int(limit, 100), 1), 500)
    query = models.Player.objects.select_related("team").prefetch_related(serializers.stat_prefetch())
    if name:
        query = query.filter(name__icontains=name.strip())
    if position:
        pos = position.strip()
        if pos.lower() == "h":
            query = query.exclude(simple_position="P")
        elif pos.lower() == "p":
            query = query.filter(simple_position="P")
        elif pos:
            query = query.filter(simple_position__icontains=pos)
    owned_bool = _bool(owned)
    if owned_bool is True:
        query = query.filter(is_owned=True)
    elif owned_bool is False:
        query = query.filter(is_owned=False)
    if team:
        club = resolve_team(team)
        query = query.filter(team=club)
    if level:
        query = query.filter(player_level__iexact=level.strip())
    if _bool(roster_40man) is True:
        query = query.filter(roster_40man=True)
    elif _bool(roster_40man) is False:
        query = query.filter(roster_40man=False)
    if _bool(roster_30man) is True:
        query = query.filter(roster_30man=True)
    elif _bool(roster_30man) is False:
        query = query.filter(roster_30man=False)
    players = list(query.order_by("last_name", "name")[:limit])
    return {
        "players": [serializers.player_brief(player) for player in players],
        "count": len(players),
    }


def list_draft_picks(
    *,
    team=None,
    year=None,
    season=None,
    draft_type=None,
    original_team=None,
    limit=500,
):
    limit = min(max(_int(limit, 500), 1), 1000)
    query = models.DraftPick.objects.select_related("team", "original_team", "player")
    if team:
        query = query.filter(team=resolve_team(team))
    if original_team:
        query = query.filter(original_team=resolve_team(original_team))
    if year:
        query = query.filter(year=str(year).strip())
    if season:
        query = query.filter(season__iexact=season.strip())
    if draft_type:
        query = query.filter(draft_type__iexact=draft_type.strip())
    picks = []
    for pick in query.order_by("-year", "draft_type", "draft_round", "pick_number")[:limit]:
        picks.append(
            {
                "id": pick.id,
                "year": pick.year,
                "season": pick.season,
                "draft_type": pick.draft_type,
                "round": pick.draft_round,
                "pick_number": pick.pick_number,
                "overall_pick_number": pick.overall_pick_number,
                "slug": pick.slug,
                "skipped": pick.skipped,
                "team": pick.team.abbreviation if pick.team_id else pick.team_name,
                "original_team": pick.original_team.abbreviation if pick.original_team_id else None,
                "player": pick.player.mlb_id if pick.player_id else None,
                "player_name": pick.player.name if pick.player_id else pick.player_name,
            }
        )
    return {"picks": picks, "count": len(picks)}


def list_trades(*, team=None, season=None, limit=200):
    limit = min(max(_int(limit, 200), 1), 500)
    query = models.Trade.objects.prefetch_related(
        "teams",
        "tradereceipt_set__team",
        "tradereceipt_set__players",
        "tradereceipt_set__picks",
    )
    if team:
        query = query.filter(teams=resolve_team(team))
    if season not in (None, ""):
        query = query.filter(season=_int(season, season))
    trades = []
    for trade in query.order_by("-date", "-id")[:limit]:
        sides = []
        for receipt in trade.tradereceipt_set.all():
            sides.append(
                {
                    "team": receipt.team.abbreviation if receipt.team_id else None,
                    "players": [
                        {"mlb_id": player.mlb_id, "name": player.name, "position": player.position}
                        for player in receipt.players.all()
                    ],
                    "picks": [
                        {
                            "year": pick.year,
                            "season": pick.season,
                            "draft_type": pick.draft_type,
                            "slug": pick.slug,
                            "round": pick.draft_round,
                        }
                        for pick in receipt.picks.all()
                    ],
                }
            )
        trades.append(
            {
                "id": str(trade.public_id),
                "date": trade.date.isoformat() if trade.date else None,
                "season": trade.season,
                "summary": trade.trade_summary,
                "teams": [club.abbreviation for club in trade.teams.all()],
                "sides": sides,
            }
        )
    return {"trades": trades, "count": len(trades)}


def list_transactions(*, team=None, year=None, limit=200):
    limit = min(max(_int(limit, 200), 1), 500)
    query = models.Transaction.objects.select_related(
        "player", "team", "acquiring_team", "transaction_type"
    )
    if team:
        club = resolve_team(team)
        query = query.filter(Q(team=club) | Q(acquiring_team=club))
    if year not in (None, ""):
        query = query.filter(date__year=_int(year, 0))
    rows = []
    for item in query.order_by("-date", "-id")[:limit]:
        kind = item.transaction_type.transaction_type if item.transaction_type_id else item.raw_transaction_type
        rows.append(
            {
                "id": item.id,
                "date": item.date.isoformat() if item.date else item.raw_date,
                "type": kind,
                "player": item.player_display,
                "mlb_id": item.player_id or item.mlb_id,
                "team": item.team.abbreviation if item.team_id else item.raw_team,
                "acquiring_team": item.acquiring_team.abbreviation if item.acquiring_team_id else item.raw_acquiring_team,
                "notes": item.notes,
                "impact_summary": item.impact_summary,
            }
        )
    return {"transactions": rows, "count": len(rows)}


def get_my_wishlist(owner):
    team = require_team(owner)
    wishlist = models.Wishlist.objects.filter(team=team).first()
    players = []
    if wishlist is not None:
        rows = (
            models.WishlistPlayer.objects.filter(wishlist=wishlist)
            .prefetch_related(
                Prefetch(
                    "player",
                    queryset=models.Player.objects.select_related("team").prefetch_related(
                        serializers.stat_prefetch()
                    ),
                )
            )
            .order_by("rank", "player__last_name")
        )
        for row in rows:
            players.append(
                {
                    "rank": row.rank,
                    "tier": row.tier,
                    "note": row.note,
                    "tags": row.tags or [],
                    "interesting": row.interesting,
                    "player_level": row.player_level,
                    "player": serializers.player_brief(row.player),
                }
            )
    return {"team": serializers.team_brief(team), "players": players}


def list_auctions(owner=None):
    team = team_for_owner(owner)
    now = timezone.now()
    auctions = (
        models.Auction.objects.filter(closes__gte=now)
        .select_related("player", "player__team")
        .prefetch_related("mlbauctionbid_set")
        .order_by("closes")
    )
    payload = []
    for auction in auctions:
        my_bid = None
        has_bids = False
        for bid in auction.mlbauctionbid_set.all():
            has_bids = True
            if team is not None and bid.team_id == team.id:
                my_bid = str(bid.max_bid_decimal) if bid.max_bid_decimal is not None else bid.max_bid
        player = auction.player
        payload.append(
            {
                "id": auction.id,
                "player": player.name if player else None,
                "mlb_id": player.mlb_id if player else None,
                "closes": auction.closes.isoformat() if auction.closes else None,
                "kind": auction.auction_kind,
                "bid_unit": auction.bid_unit,
                "min_bid": auction.min_bid,
                "is_nomination": auction.is_nomination,
                "has_bids": has_bids,
                "my_bid": my_bid,
            }
        )
    return {"auctions": payload, "count": len(payload)}


def list_team_ledger(abbreviation=None, owner=None, year=None, book=None):
    team = require_team(owner, abbreviation)
    ledger_year = _int(year, None) if year not in (None, "") else getattr(settings, "LEAGUE_YEAR", None)
    query = models.ClubLedgerEntry.objects.filter(team=team)
    if ledger_year:
        query = query.filter(year=ledger_year)
    if book:
        query = query.filter(book=book.strip().lower())
    entries = [
        {
            "year": entry.year,
            "book": entry.book,
            "label": entry.label,
            "detail": entry.detail,
            "amount": entry.amount,
        }
        for entry in query.order_by("year", "book", "row_order", "id")
    ]
    return {
        "team": serializers.team_brief(team),
        "year": ledger_year,
        "entries": entries,
    }
