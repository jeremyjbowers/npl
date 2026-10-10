"""Open proposals that have not been processed on Monday.

Roster rows and club finances still show the official club. These helpers
describe the overlay: who would leave, and how cash, cap space, and IFA
pool space would move.
"""

from django.utils import timezone

from npl import models
from npl.transactions.catalog import ASSET_CASH, ASSET_CARRIED_SALARY, ASSET_IFA, SIGNING_CODES

OPEN_STATUSES = (
    models.TransactionProposal.DRAFT,
    models.TransactionProposal.PROPOSED,
    models.TransactionProposal.AWAITING,
    models.TransactionProposal.AGREED,
)

# A player in one of these filings is leaving the club if the proposal clears.
DEPARTURE_KINDS = {
    "trade": "Pending trade",
    "release": "Pending release",
    "non_tender": "Pending non-tender",
    "waiver_request_outright": "Pending outright waivers",
    "waiver_request_trade": "Pending trade waivers",
    "waiver_request_rule5": "Pending Rule 5 waivers",
    "foreign_place": "Pending foreign list",
    "retirement": "Pending retirement",
    "death": "Pending removal",
}

FORTY_MAN_ADDS = {"purchase_contract", "mlb_signing", "in_season_fa"}
FORTY_MAN_DROPS = {
    "release",
    "non_tender",
    "retirement",
    "death",
    "foreign_place",
    "waiver_request_outright",
}


def open_proposals():
    return list(
        models.TransactionProposal.objects.filter(status__in=OPEN_STATUSES)
        .select_related("originating_team")
        .prefetch_related("assets__player", "assets__from_team", "assets__to_team")
    )


def _signing_cap_hit(assets, contract_terms):
    if isinstance(contract_terms, dict) and contract_terms.get("total"):
        return int(contract_terms["total"])
    for asset in assets:
        terms = asset.get("contract_terms") or {}
        if isinstance(terms, dict) and terms.get("total"):
            return int(terms["total"])
        if asset.get("amount"):
            return int(asset["amount"])
    return 0


def _current_salary(player, team):
    contract = models.Contract.objects.filter(player=player, team=team).first()
    if contract is None:
        return 0
    year = models.ContractYear.objects.filter(
        contract=contract, year=timezone.localdate().year
    ).first()
    return year.amount if year else 0


def money_moves(code, team, assets, contract_terms=None):
    """Dollar moves as (team_id, field, delta). Field is cash, cap, or ifa."""
    moves = []
    for asset in assets:
        amount = asset.get("amount")
        if not amount:
            continue
        amount = int(amount)
        kind = asset.get("asset_type")
        origin = asset.get("from_team")
        dest = asset.get("to_team")
        if kind == ASSET_CASH:
            if origin is not None:
                moves.append((origin.id, "cash", -amount))
            if dest is not None:
                moves.append((dest.id, "cash", amount))
        elif kind == ASSET_IFA:
            if origin is not None:
                moves.append((origin.id, "ifa", -amount))
            if dest is not None:
                moves.append((dest.id, "ifa", amount))
        elif kind == ASSET_CARRIED_SALARY:
            if origin is not None:
                moves.append((origin.id, "cap", amount))
            if dest is not None:
                moves.append((dest.id, "cap", -amount))
    if code in SIGNING_CODES and code != "ifa_signing":
        hit = _signing_cap_hit(assets, contract_terms)
        if hit and team is not None:
            moves.append((team.id, "cap", -hit))
    if code == "ifa_signing":
        bonus = _signing_cap_hit(assets, contract_terms)
        if bonus and team is not None:
            moves.append((team.id, "ifa", -bonus))
    if code in ("release", "non_tender") and team is not None:
        for asset in assets:
            player = asset.get("player")
            if player is None:
                continue
            salary = _current_salary(player, team)
            if salary:
                moves.append((team.id, "cap", salary))
    return moves


def forty_man_delta(code, team, assets):
    """How this filing would change the club's 40-man count."""
    delta = 0
    if code in FORTY_MAN_ADDS:
        players = [
            asset.get("player")
            for asset in assets
            if asset.get("asset_type") == "player" and asset.get("player") is not None
        ]
        if not players:
            delta += 1
        for player in players:
            if not player.roster_40man or player.team_id != team.id:
                delta += 1
    if code in FORTY_MAN_DROPS:
        for asset in assets:
            player = asset.get("player")
            if player is not None and player.roster_40man and player.team_id == team.id:
                delta -= 1
    if code == "trade":
        for asset in assets:
            player = asset.get("player")
            if player is None or not player.roster_40man:
                continue
            origin = asset.get("from_team")
            dest = asset.get("to_team")
            if origin is not None and origin.id == team.id:
                delta -= 1
            if dest is not None and dest.id == team.id and player.team_id != team.id:
                delta += 1
    return delta


def _blank_money():
    return {"cash": 0, "cap": 0, "ifa": 0}


def money_for_teams(proposals):
    """team id -> cash/cap/ifa deltas from every open proposal."""
    totals = {}
    for proposal in proposals:
        for team_id, field, delta in money_moves(
            proposal.kind,
            proposal.originating_team,
            [_asset_dict(asset) for asset in proposal.assets.all()],
            proposal.contract_terms,
        ):
            bucket = totals.setdefault(team_id, _blank_money())
            bucket[field] += delta
    return totals


def hints_for_team(team, proposals):
    """player id -> the open proposal that would take him off this club."""
    hints = {}
    for proposal in proposals:
        if proposal.kind not in DEPARTURE_KINDS:
            continue
        for asset in proposal.assets.all():
            player = asset.player
            if player is None or player.team_id != team.id:
                continue
            origin = asset.from_team
            if proposal.kind == "trade" and (origin is None or origin.id != team.id):
                continue
            if player.pk in hints:
                continue
            hints[player.pk] = {
                "proposal_id": proposal.id,
                "label": DEPARTURE_KINDS[proposal.kind],
                "url": f"/transactions/proposals/{proposal.id}/",
            }
    return hints


def annotate_players(players, hints):
    marked = list(players)
    for player in marked:
        hint = hints.get(player.pk)
        if hint:
            player.pending_hint = hint
    return marked


def _asset_dict(asset):
    return {
        "asset_type": asset.asset_type,
        "player": asset.player,
        "from_team": asset.from_team,
        "to_team": asset.to_team,
        "amount": asset.amount,
        "contract_terms": asset.contract_terms,
    }


def attach_money(team, totals):
    """Set pending_* attributes used by the team cards and the club page."""
    bucket = totals.get(team.id) or _blank_money()
    team.pending_cash_delta = bucket["cash"] or None
    team.pending_cap_delta = bucket["cap"] or None
    team.pending_ifa_delta = bucket["ifa"] or None
    team.pending_cash_after = None if team.cash is None or not bucket["cash"] else team.cash + bucket["cash"]
    team.pending_cap_after = None if team.cap_space is None or not bucket["cap"] else team.cap_space + bucket["cap"]
    team.pending_ifa_after = None if team.ifa is None or not bucket["ifa"] else team.ifa + bucket["ifa"]
    return team
