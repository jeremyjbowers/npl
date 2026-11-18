"""Read-only lookups shared by the MCP JSON API and in-process tools."""

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from npl import models
from npl.mcp_app import serializers
from npl.rosters import build_sections, is_active_mlb
from npl.transactions.catalog import normalize_sheet_type, sheet_asset_type
from npl.transactions.clubs import FRANCHISES, franchise_number
from npl.transactions.impact import (
    FORTY_LIMIT,
    RESERVE_LIMIT,
    counts_on_forty,
    counts_on_reserve,
    roster_roundup,
)
from npl.transactions.trades import archive_trade_groups, trade_rows_q


MONEY_ASSETS = {"cash", "ifa_pool", "cap_space", "carried_salary", "coverage"}
ARRIVE_CODES = {
    "trade",
    "waiver_claimed",
    "mlb_signing",
    "in_season_fa",
    "minor_signing",
    "ifa_signing",
    "rule5_draft",
    "rule4_draft",
    "auction_result",
    "waiver_returned_rule5",
}
LEAVE_CODES = {"release", "non_tender", "retirement", "death", "contract_amnesty"}
WAR_NOTE = (
    "WAR is each player's full MLB season, whichever NPL club he played for. "
    "It is not split by club. npl_lines are the simulated stats for each NPL club "
    "and do not include that WAR. stints on get_player name the clubs and the dates."
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


def _club_labels(team):
    number = (
        franchise_number(team.tab_id)
        or franchise_number(team.short_name)
        or franchise_number(team.full_name)
    )
    labels = set()
    if number:
        labels.update(FRANCHISES[number])
    for value in (team.abbreviation, team.short_name, team.full_name, team.tab_id):
        if value:
            labels.add(value)
    return labels


class ClubDirectory:
    """Resolve a sheet label to the current club without a query per row."""

    def __init__(self):
        self.by_number = {}
        for team in models.Team.objects.all():
            number = (
                franchise_number(team.tab_id)
                or franchise_number(team.short_name)
                or franchise_number(team.full_name)
            )
            if number and number not in self.by_number:
                self.by_number[number] = team

    def resolve(self, team, raw):
        if team is not None:
            return team
        number = franchise_number(raw)
        if number is None:
            return None
        return self.by_number.get(number)


def search_players(
    *,
    name=None,
    position=None,
    owned=None,
    team=None,
    level=None,
    roster_40man=None,
    roster_30man=None,
    pool=None,
    season=None,
    sort=None,
    offset=0,
    limit=100,
):
    limit = min(max(_int(limit, 100), 1), 500)
    offset = max(_int(offset, 0), 0)
    order = (sort or "name").strip().lower()
    if order not in {"name", "war"}:
        order = "name"
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
    if pool:
        listings = models.FreeAgentListing.objects.filter(pool=pool.strip())
        if season not in (None, ""):
            listings = listings.filter(season_year=_int(season, 0))
        query = query.filter(mlb_id__in=listings.values("player_id"))
    total = query.count()
    if order == "war":
        players = list(query)
        players.sort(key=_war_sort_key)
        players = players[offset : offset + limit]
    else:
        players = list(query.order_by("last_name", "name")[offset : offset + limit])
    return {
        "players": [serializers.player_brief(player) for player in players],
        "count": len(players),
        "total": total,
        "offset": offset,
        "limit": limit,
        "sort": order,
    }


def _war_sort_key(player):
    value, _season = serializers.war_record(player)
    name = ((player.last_name or ""), (player.name or ""))
    if value is None:
        return (1, 0, name)
    return (0, -value, name)


def list_free_agents(
    *,
    name=None,
    position=None,
    level=None,
    pool=None,
    season=None,
    sort=None,
    offset=0,
    limit=200,
):
    """Unowned players, best full-season MLB WAR first."""
    payload = search_players(
        name=name,
        position=position,
        owned=False,
        level=level,
        pool=pool,
        season=season,
        sort=sort or "war",
        offset=offset,
        limit=limit,
    )
    payload["war_note"] = WAR_NOTE
    return payload


def list_draft_picks(
    *,
    team=None,
    year=None,
    season=None,
    draft_type=None,
    original_team=None,
    held=None,
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
    held_bool = _bool(held)
    if held_bool is True:
        query = query.filter(player__isnull=True, skipped=False)
    elif held_bool is False:
        query = query.exclude(player__isnull=True, skipped=False)
    picks = []
    for pick in query.order_by("-year", "draft_type", "draft_round", "pick_number")[:limit]:
        unused = pick.player_id is None and not pick.skipped
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
                "held": unused,
                "pick_notes": pick.pick_notes,
                "team": pick.team.abbreviation if pick.team_id else serializers.sheet_label(pick.team_name),
                "team_name": serializers.club_name(pick.team, pick.team_name),
                "original_team": pick.original_team.abbreviation if pick.original_team_id else None,
                "original_team_name": serializers.club_name(pick.original_team) if pick.original_team_id else None,
                "player": pick.player.mlb_id if pick.player_id else None,
                "player_name": pick.player.name if pick.player_id else pick.player_name,
            }
        )
    return {"picks": picks, "count": len(picks)}


def list_pick_inventory(
    *,
    team=None,
    year=None,
    season=None,
    draft_type=None,
    limit=1000,
):
    """Draft picks a club still holds: no player has been taken and the pick was not skipped."""
    payload = list_draft_picks(
        team=team,
        year=year,
        season=season,
        draft_type=draft_type,
        held=True,
        limit=limit,
    )
    clubs = []
    index = {}
    for pick in payload["picks"]:
        key = pick["team"] or pick["team_name"] or "Unassigned"
        if key not in index:
            index[key] = {"team": pick["team"], "team_name": pick["team_name"], "picks": []}
            clubs.append(index[key])
        index[key]["picks"].append(pick)
    return {"clubs": clubs, "picks": payload["picks"], "count": payload["count"]}


def _row_code(row):
    kind = getattr(row, "transaction_type", None)
    if kind is not None and getattr(kind, "code", None):
        return kind.code
    return normalize_sheet_type(getattr(row, "raw_transaction_type", None)) or ""


def _asset_for(row):
    asset = sheet_asset_type(getattr(row, "raw_player", None))
    draft = serializers.sheet_label(getattr(row, "raw_draft_pick", None))
    if draft and not asset:
        asset = "draft_pick"
    if getattr(row, "player_id", None) and not asset:
        asset = "player"
    if getattr(row, "cash_considerations", None) is not None and not asset:
        asset = "cash"
    return asset or "other"


def transaction_piece(row, directory):
    """One ledger line: the player, pick, or money, and both club names."""
    origin = directory.resolve(row.team if getattr(row, "team_id", None) else None, row.raw_team)
    landing = directory.resolve(
        row.acquiring_team if getattr(row, "acquiring_team_id", None) else None,
        row.raw_acquiring_team,
    )
    asset = _asset_for(row)
    draft = serializers.sheet_label(row.raw_draft_pick)
    if asset == "draft_pick" and not draft:
        draft = serializers.sheet_label(row.notes)
    player_name = None
    if asset == "player" or getattr(row, "player_id", None):
        player_name = row.player.name if getattr(row, "player_id", None) and row.player else row.player_display
    return {
        "asset": asset,
        "label": row.player_display,
        "player": player_name,
        "mlb_id": row.player_id or row.mlb_id or None,
        "position": row.player.position if getattr(row, "player_id", None) and row.player else None,
        "draft_pick": draft,
        "cash": row.cash_considerations,
        "notes": row.notes,
        "from_team": serializers.club_token(origin, row.raw_team),
        "from_team_name": serializers.club_name(origin, row.raw_team),
        "to_team": serializers.club_token(landing, row.raw_acquiring_team),
        "to_team_name": serializers.club_name(landing, row.raw_acquiring_team),
        "from": serializers.club_dict(origin, row.raw_team),
        "to": serializers.club_dict(landing, row.raw_acquiring_team),
    }


def _legacy_pieces(trade):
    pieces = []
    for receipt in trade.tradereceipt_set.all():
        landing = receipt.team
        for player in receipt.players.all():
            pieces.append(
                {
                    "asset": "player",
                    "label": player.name,
                    "player": player.name,
                    "mlb_id": player.mlb_id,
                    "position": player.position,
                    "draft_pick": None,
                    "cash": None,
                    "notes": None,
                    "from_team": None,
                    "from_team_name": None,
                    "to_team": serializers.club_token(landing),
                    "to_team_name": serializers.club_name(landing),
                    "from": None,
                    "to": serializers.club_dict(landing),
                }
            )
        for pick in receipt.picks.all():
            description = pick.slug or " ".join(
                part
                for part in (
                    pick.year,
                    pick.season,
                    pick.draft_type,
                    f"round {pick.draft_round}" if pick.draft_round else None,
                )
                if part
            )
            pieces.append(
                {
                    "asset": "draft_pick",
                    "label": description,
                    "player": None,
                    "mlb_id": None,
                    "position": None,
                    "draft_pick": description,
                    "pick_year": pick.year,
                    "pick_season": pick.season,
                    "pick_type": pick.draft_type,
                    "pick_round": pick.draft_round,
                    "pick_slug": pick.slug,
                    "cash": None,
                    "notes": None,
                    "from_team": None,
                    "from_team_name": None,
                    "to_team": serializers.club_token(landing),
                    "to_team_name": serializers.club_name(landing),
                    "from": None,
                    "to": serializers.club_dict(landing),
                }
            )
    return pieces


def _sides_from_pieces(pieces):
    order = []
    buckets = {}
    for piece in pieces:
        key = piece.get("to_team") or piece.get("to_team_name") or "Unknown"
        if key not in buckets:
            buckets[key] = {
                "team": piece.get("to_team"),
                "team_name": piece.get("to_team_name"),
                "players": [],
                "picks": [],
                "cash": [],
                "receives": [],
            }
            order.append(key)
        bucket = buckets[key]
        bucket["receives"].append(piece)
        if piece.get("asset") == "draft_pick" or piece.get("draft_pick"):
            bucket["picks"].append(
                {
                    "year": piece.get("pick_year"),
                    "season": piece.get("pick_season"),
                    "draft_type": piece.get("pick_type"),
                    "slug": piece.get("pick_slug"),
                    "round": piece.get("pick_round"),
                    "description": piece.get("draft_pick") or piece.get("label"),
                }
            )
        elif piece.get("player") or piece.get("mlb_id"):
            bucket["players"].append(
                {
                    "mlb_id": piece.get("mlb_id"),
                    "name": piece.get("player") or piece.get("label"),
                    "position": piece.get("position"),
                }
            )
        if piece.get("cash") is not None:
            bucket["cash"].append(piece["cash"])
    return [buckets[key] for key in order]


def _trade_summary(date, sides):
    parts = []
    for side in sides:
        bits = [player["name"] for player in side["players"] if player.get("name")]
        bits.extend(pick["description"] for pick in side["picks"] if pick.get("description"))
        bits.extend(f"${amount:,}" for amount in side["cash"])
        who = side.get("team_name") or side.get("team")
        if bits and who:
            parts.append(f"{who} receives {', '.join(bits)}")
    if not parts:
        return None
    when = date.isoformat() if hasattr(date, "isoformat") else (date or "")
    return f"{when}: {'; '.join(parts)}.".strip()


def _merge_pieces(ledger_pieces, legacy_pieces):
    seen_players = {piece["mlb_id"] for piece in ledger_pieces if piece.get("mlb_id")}
    seen_picks = {piece["draft_pick"] for piece in ledger_pieces if piece.get("draft_pick")}
    pieces = list(ledger_pieces)
    for extra in legacy_pieces:
        if extra.get("mlb_id") and extra["mlb_id"] in seen_players:
            continue
        if extra.get("draft_pick") and extra["draft_pick"] in seen_picks:
            continue
        pieces.append(extra)
    return pieces


def _club_list(trade, pieces):
    clubs = []
    tokens = []

    def add(club):
        if not club:
            return
        key = club.get("abbreviation") or club.get("name") or club.get("sheet_name")
        if not key or key in tokens:
            return
        tokens.append(key)
        clubs.append(club)

    if trade is not None:
        for team in trade.teams.all():
            add(serializers.club_dict(team))
    for piece in pieces:
        add(piece.get("from"))
        add(piece.get("to"))
    return clubs


def _trade_payload(trade, rows, directory):
    ledger = [transaction_piece(row, directory) for row in rows]
    legacy = _legacy_pieces(trade) if trade is not None else []
    pieces = _merge_pieces(ledger, legacy)
    sides = _sides_from_pieces(pieces)
    when = trade.date if trade is not None and trade.date else (rows[0].date if rows else None)
    summary = None
    if trade is not None and (trade.trade_summary or "").strip():
        summary = trade.trade_summary
    else:
        summary = _trade_summary(when, sides)
    clubs = _club_list(trade, pieces)
    return {
        "id": str(trade.public_id) if trade is not None else None,
        "date": when.isoformat() if when else None,
        "season": trade.season if trade is not None else (when.year if when else None),
        "summary": summary,
        "teams": [club["abbreviation"] or club["name"] for club in clubs if club.get("abbreviation") or club.get("name")],
        "clubs": clubs,
        "sides": sides,
        "pieces": pieces,
    }


def _team_clause(club):
    clause = Q(team=club) | Q(acquiring_team=club)
    for label in _club_labels(club):
        clause |= Q(raw_team__iexact=label) | Q(raw_acquiring_team__iexact=label)
    return clause


def _row_involves(row, club, directory):
    if row.team_id == club.id or row.acquiring_team_id == club.id:
        return True
    labels = {serializers.sheet_label(label).lower() for label in _club_labels(club) if serializers.sheet_label(label)}
    for raw in (row.raw_team, row.raw_acquiring_team):
        text = serializers.sheet_label(raw)
        if text and text.lower() in labels:
            return True
        resolved = directory.resolve(None, raw)
        if resolved is not None and resolved.id == club.id:
            return True
    return False


def list_trades(*, team=None, season=None, limit=200):
    """Trades with the players, picks, and cash on each side.

    Posted deals keep those pieces on ledger lines. Older deals may only
    have a TradeReceipt. Deals that were never given a trade id are still
    grouped from the ledger.
    """
    limit = min(max(_int(limit, 200), 1), 500)
    season_year = _int(season, None) if season not in (None, "") else None
    directory = ClubDirectory()
    club = resolve_team(team) if team else None
    query = models.Trade.objects.prefetch_related(
        "teams",
        "tradereceipt_set__team",
        "tradereceipt_set__players",
        "tradereceipt_set__picks__team",
        Prefetch(
            "receipts",
            queryset=models.Transaction.objects.select_related(
                "player", "team", "acquiring_team", "transaction_type"
            ).order_by("date", "id"),
        ),
    )
    if club is not None:
        clause = Q(teams=club) | Q(receipts__team=club) | Q(receipts__acquiring_team=club)
        for label in _club_labels(club):
            clause |= Q(receipts__raw_team__iexact=label) | Q(receipts__raw_acquiring_team__iexact=label)
        query = query.filter(clause).distinct()
    if season_year is not None:
        query = query.filter(season=season_year)
    trades = [
        _trade_payload(trade, list(trade.receipts.all()), directory)
        for trade in query.order_by("-date", "-id")
    ]

    unlinked = (
        models.Transaction.objects.filter(trade__isnull=True)
        .filter(trade_rows_q())
        .select_related("player", "team", "acquiring_team", "transaction_type")
        .order_by("-date", "-id")
    )
    if season_year is not None:
        unlinked = unlinked.filter(date__year=season_year)
    groups = archive_trade_groups(list(unlinked))
    for group in groups:
        if club is not None and not any(_row_involves(row, club, directory) for row in group):
            continue
        if season_year is not None and (not group[0].date or group[0].date.year != season_year):
            continue
        trades.append(_trade_payload(None, group, directory))
    trades.sort(key=lambda item: (item["date"] or "", item["id"] or ""), reverse=True)
    total = len(trades)
    trades = trades[:limit]
    return {"trades": trades, "count": len(trades), "total": total}


def list_transactions(*, team=None, year=None, limit=200):
    limit = min(max(_int(limit, 200), 1), 500)
    query = models.Transaction.objects.select_related(
        "player", "team", "acquiring_team", "transaction_type", "trade"
    )
    directory = ClubDirectory()
    if team:
        query = query.filter(_team_clause(resolve_team(team)))
    if year not in (None, ""):
        query = query.filter(date__year=_int(year, 0))
    total = query.count()
    rows = []
    for item in query.order_by("-date", "-id")[:limit]:
        kind = item.transaction_type.transaction_type if item.transaction_type_id else item.raw_transaction_type
        origin = directory.resolve(item.team if item.team_id else None, item.raw_team)
        landing = directory.resolve(
            item.acquiring_team if item.acquiring_team_id else None,
            item.raw_acquiring_team,
        )
        piece = transaction_piece(item, directory)
        rows.append(
            {
                "id": item.id,
                "date": item.date.isoformat() if item.date else item.raw_date,
                "type": kind,
                "player": item.player_display,
                "mlb_id": item.player_id or item.mlb_id,
                "team": serializers.club_token(origin, item.raw_team),
                "team_name": serializers.club_name(origin, item.raw_team),
                "acquiring_team": serializers.club_token(landing, item.raw_acquiring_team),
                "acquiring_team_name": serializers.club_name(landing, item.raw_acquiring_team),
                "cash": item.cash_considerations,
                "draft_pick": piece["draft_pick"],
                "asset": piece["asset"],
                "notes": item.notes,
                "impact_summary": item.impact_summary,
                "trade_id": str(item.trade.public_id) if item.trade_id else None,
            }
        )
    return {"transactions": rows, "count": len(rows), "total": total}


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
        "payroll_lines": _payroll_lines(team, ledger_year),
    }


def _payroll_lines(team, year):
    """Contract salaries. Ledger entries are the adjustments, not these lines."""
    contracts = (
        models.Contract.objects.filter(team=team)
        .select_related("player")
        .prefetch_related("contractyear_set")
        .order_by("player__last_name", "player__name", "id")
    )
    lines = []
    for contract in contracts:
        player = contract.player
        for item in contract.contractyear_set.all():
            if year and item.year != int(year):
                continue
            lines.append(
                {
                    "year": item.year,
                    "player": player.name if player else None,
                    "mlb_id": player.mlb_id if player else None,
                    "position": player.position if player else None,
                    "amount": item.amount,
                    "salary_class": item.salary_class,
                    "salary_label": item.salary_label,
                    "terms_pending": contract.terms_pending,
                    "buyout_amount": contract.buyout_amount if contract.can_buyout else None,
                    "notes": contract.notes,
                }
            )
    return lines


def _same_club(stint, team):
    if stint is None or team is None:
        return False
    if stint.get("team_id") and team.id:
        return stint["team_id"] == team.id
    return stint.get("team_name") == serializers.club_name(team)


def _player_row(row):
    asset = _asset_for(row)
    if asset in MONEY_ASSETS or asset == "draft_pick":
        return False
    return bool(getattr(row, "player_id", None) or getattr(row, "mlb_id", None))


def player_stints(player, rows, directory):
    """Clubs that received or released the player, in date order."""
    stints = []
    open_stint = None

    def close(date):
        nonlocal open_stint
        if open_stint is not None and open_stint["end"] is None:
            open_stint["end"] = date.isoformat() if date else None
            open_stint = None

    def open_on(team, raw, date, via):
        nonlocal open_stint
        if team is None and serializers.sheet_label(raw) is None:
            return
        if _same_club(open_stint, team) and open_stint["end"] is None:
            return
        close(date)
        open_stint = {
            "team_id": team.id if team is not None else None,
            "team": serializers.club_token(team, raw),
            "team_name": serializers.club_name(team, raw),
            "start": date.isoformat() if date else None,
            "end": None,
            "current": False,
            "via": via,
        }
        stints.append(open_stint)

    for row in rows:
        if not _player_row(row):
            continue
        code = _row_code(row)
        origin = directory.resolve(row.team if row.team_id else None, row.raw_team)
        landing = directory.resolve(
            row.acquiring_team if row.acquiring_team_id else None,
            row.raw_acquiring_team,
        )
        if code in LEAVE_CODES:
            close(row.date)
            continue
        if code not in ARRIVE_CODES:
            continue
        if code == "trade":
            if origin is not None and not _same_club(open_stint, origin):
                if open_stint is None or open_stint["end"] is not None:
                    stints.append(
                        {
                            "team_id": origin.id,
                            "team": serializers.club_token(origin, row.raw_team),
                            "team_name": serializers.club_name(origin, row.raw_team),
                            "start": None,
                            "end": row.date.isoformat() if row.date else None,
                            "current": False,
                            "via": "trade",
                        }
                    )
                else:
                    close(row.date)
            elif open_stint is not None:
                close(row.date)
            if landing is not None:
                open_on(landing, row.raw_acquiring_team, row.date, "trade")
            continue
        open_on(landing or origin, row.raw_acquiring_team or row.raw_team, row.date, code)

    if player.team_id:
        if _same_club(open_stint, player.team) and open_stint["end"] is None:
            open_stint["current"] = True
        else:
            stints.append(
                {
                    "team_id": player.team_id,
                    "team": player.team.abbreviation,
                    "team_name": player.team.short_name,
                    "start": open_stint["end"] if open_stint else None,
                    "end": None,
                    "current": True,
                    "via": "roster",
                }
            )
    for stint in stints:
        stint.pop("team_id", None)
    return stints


def get_player(mlb_id):
    key = (mlb_id or "").strip()
    player = (
        models.Player.objects.select_related("team")
        .prefetch_related(serializers.stat_prefetch(), serializers.contract_prefetch())
        .filter(mlb_id=key)
        .first()
    )
    if player is None:
        raise models.Player.DoesNotExist(key)
    directory = ClubDirectory()
    rows = list(
        models.Transaction.objects.filter(Q(player=player) | Q(mlb_id=player.mlb_id))
        .select_related("player", "team", "acquiring_team", "transaction_type")
        .order_by("date", "id")
    )
    return {
        "player": serializers.player_brief(player),
        "stints": player_stints(player, rows, directory),
        "stint_note": (
            "Stints are the NPL clubs that received or released this player. "
            "Full-season MLB WAR is not divided across them."
        ),
        "war_note": WAR_NOTE,
    }
