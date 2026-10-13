"""What a filing does to cap space and to the 40-man and 85-man counts.

The weekly roster check uses the same counts. End-of-season IL and a
foreign-list assignment take a player off both lists. A release does too.
"""

from collections import defaultdict

from npl import models
from npl.transactions.pending import forty_man_delta, money_moves, open_proposals

FORTY_LIMIT = 40
RESERVE_LIMIT = 85

RESERVE_ADDS = {
    "mlb_signing",
    "in_season_fa",
    "minor_signing",
    "ifa_signing",
    "rule4_draft",
    "rule5_draft",
}
RESERVE_DROPS = {
    "release",
    "contract_amnesty",
    "non_tender",
    "retirement",
    "death",
    "foreign_place",
    "il_eos",
}

MONEY_LABELS = {
    "cap": "cap space",
    "cash": "cash",
    "ifa": "IFA pool space",
}


def counts_on_forty(player):
    return bool(player.roster_40man) and not player.roster_eosIL and not player.roster_foreign


def counts_on_reserve(player):
    return not (player.roster_eosIL or player.roster_foreign or player.roster_retired)


def reserve_delta(code, team, assets):
    """How this filing would change the club's 85-man count."""
    delta = 0
    players = [
        asset.get("player")
        for asset in assets
        if asset.get("asset_type") == "player" and asset.get("player") is not None
    ]
    if code in RESERVE_ADDS:
        incoming = [player for player in players if player.team_id != team.id]
        delta += len(incoming) if players else 1
    if code in RESERVE_DROPS:
        for player in players:
            if player.team_id == team.id and counts_on_reserve(player):
                delta -= 1
    if code == "trade":
        for asset in assets:
            if asset.get("asset_type") != "player":
                continue
            player = asset.get("player")
            if player is None or not counts_on_reserve(player):
                continue
            origin = asset.get("from_team")
            dest = asset.get("to_team")
            if origin is not None and origin.id == team.id:
                delta -= 1
            if dest is not None and dest.id == team.id and player.team_id != team.id:
                delta += 1
    return delta


def _players(count):
    count = abs(int(count))
    return "1 player" if count == 1 else f"{count} players"


def _money_line(name, field, delta):
    if not delta:
        return None
    amount = f"${abs(int(delta)):,}"
    label = MONEY_LABELS[field]
    if delta > 0:
        return f"{name} adds {amount} to {label}."
    return f"{name} removes {amount} from {label}."


def _count_line(name, delta, roster):
    if not delta:
        return None
    if delta > 0:
        return f"{name} adds {_players(delta)} to the {roster}."
    return f"{name} removes {_players(delta)} from the {roster}."


def _player_label(assets, team_id):
    names = []
    for asset in assets:
        player = asset.get("player")
        if player is None:
            continue
        origin = asset.get("from_team")
        if origin is not None and origin.id != team_id and getattr(player, "team_id", None) != team_id:
            continue
        names.append(player.name)
    if not names:
        return "the player"
    return ", ".join(names)


def impact_lines(code, team, assets, contract_terms=None):
    """Sentences describing this filing. One sentence per money or roster change."""
    clubs = {}

    def remember(club):
        if club is not None and getattr(club, "id", None) is not None:
            clubs[club.id] = club

    remember(team)
    for asset in assets or []:
        remember(asset.get("from_team"))
        remember(asset.get("to_team"))

    money = defaultdict(lambda: {"cash": 0, "cap": 0, "ifa": 0})
    for team_id, field, delta in money_moves(code, team, assets or [], contract_terms):
        money[team_id][field] += delta

    order = list(clubs)
    for team_id in money:
        if team_id not in clubs:
            order.append(team_id)

    lines = []
    for team_id in order:
        club = clubs.get(team_id)
        name = club.short_name if club is not None else "Club"
        bucket = money.get(team_id) or {}
        for field in ("cap", "cash", "ifa"):
            line = _money_line(name, field, bucket.get(field, 0))
            if line:
                lines.append(line)
        if club is None:
            continue
        forty = forty_man_delta(code, club, assets or [])
        reserve = reserve_delta(code, club, assets or [])
        if code in {"il_eos", "foreign_place"} and (forty or reserve):
            who = _player_label(assets or [], team_id)
            if code == "il_eos":
                action = f"{name} reclassifies {who} to the end-of-season IL."
            else:
                action = f"{name} places {who} on the foreign list."
            effects = []
            if forty:
                effects.append(_count_line(name, forty, "40-man").replace(f"{name} ", "", 1))
            if reserve:
                effects.append(_count_line(name, reserve, "85-man").replace(f"{name} ", "", 1))
            lines.append(action + " " + " ".join(sentence[0].upper() + sentence[1:] for sentence in effects))
            continue
        for line in (_count_line(name, forty, "40-man"), _count_line(name, reserve, "85-man")):
            if line:
                lines.append(line)
    if not lines:
        return ["No cap, cash, or roster change."]
    return lines


def lines_for_proposal(proposal):
    assets = [
        {
            "asset_type": asset.asset_type,
            "player": asset.player,
            "from_team": asset.from_team,
            "to_team": asset.to_team,
            "amount": asset.amount,
            "contract_terms": asset.contract_terms,
        }
        for asset in proposal.assets.all()
    ]
    return impact_lines(proposal.kind, proposal.originating_team, assets, proposal.contract_terms)


def obligation_lines(name, forty, reserve, pending_forty=0, pending_reserve=0):
    """Moves this club still has to make. Empty when both lists are legal."""
    lines = []
    if forty > FORTY_LIMIT:
        extra = forty - FORTY_LIMIT
        them = "him" if extra == 1 else "them"
        lines.append(
            f"{name} has {forty} players on the 40-man and must remove {extra}, "
            f"either by waiving a player or reclassifying {them} to the end-of-season IL or a foreign league."
        )
    elif forty + pending_forty > FORTY_LIMIT:
        projected = forty + pending_forty
        extra = projected - FORTY_LIMIT
        lines.append(
            f"{name} would have {projected} players on the 40-man if open filings clear, and would need to remove {extra}."
        )
    if reserve > RESERVE_LIMIT:
        extra = reserve - RESERVE_LIMIT
        lines.append(
            f"{name} has {reserve} players on the 85-man and must drop or reclassify {extra}."
        )
    elif reserve + pending_reserve > RESERVE_LIMIT:
        projected = reserve + pending_reserve
        extra = projected - RESERVE_LIMIT
        lines.append(
            f"{name} would have {projected} players on the 85-man if open filings clear, and would need to drop or reclassify {extra}."
        )
    return lines


def _asset_dict(asset):
    return {
        "asset_type": asset.asset_type,
        "player": asset.player,
        "from_team": asset.from_team,
        "to_team": asset.to_team,
        "amount": asset.amount,
        "contract_terms": asset.contract_terms,
    }


def roster_roundup():
    """Clubs that are over a roster limit, or would be once open filings clear."""
    players = models.Player.objects.exclude(team_id=None).only(
        "mlb_id",
        "team_id",
        "roster_40man",
        "roster_eosIL",
        "roster_foreign",
        "roster_retired",
    )
    grouped = defaultdict(list)
    for player in players:
        grouped[player.team_id].append(player)

    pending_forty = defaultdict(int)
    pending_reserve = defaultdict(int)
    for proposal in open_proposals():
        assets = [_asset_dict(asset) for asset in proposal.assets.all()]
        involved = {proposal.originating_team_id}
        for asset in assets:
            if asset["from_team"] is not None:
                involved.add(asset["from_team"].id)
            if asset["to_team"] is not None:
                involved.add(asset["to_team"].id)
        for team_id in involved:
            if team_id is None:
                continue
            club = type("Club", (), {"id": team_id})()
            pending_forty[team_id] += forty_man_delta(proposal.kind, club, assets)
            pending_reserve[team_id] += reserve_delta(proposal.kind, club, assets)

    rows = []
    for team in models.Team.objects.all().order_by("short_name"):
        members = grouped.get(team.id, [])
        forty = sum(1 for player in members if counts_on_forty(player))
        reserve = sum(1 for player in members if counts_on_reserve(player))
        lines = obligation_lines(
            team.short_name,
            forty,
            reserve,
            pending_forty[team.id],
            pending_reserve[team.id],
        )
        if not lines:
            continue
        rows.append(
            {
                "team": team,
                "forty": forty,
                "reserve": reserve,
                "lines": lines,
            }
        )
    return rows
