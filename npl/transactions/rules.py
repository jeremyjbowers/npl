"""Reject filings that the roster and the books cannot support.

Directors still judge close calls. These checks stop the filings that are
already false: a player who is not on the club, a second open deal for the
same player, a 40-man that would not fit, or cash and pool space the club
does not have.
"""

from npl import models
from npl.transactions.pending import (
    FORTY_MAN_ADDS,
    FORTY_MAN_DROPS,
    forty_man_delta,
    money_moves,
    open_proposals,
)
MUST_BE_ON_CLUB = {
    "il_7",
    "il_56",
    "il_eos",
    "il_covid",
    "il_move",
    "il_activate",
    "in_limbo",
    "option_minors",
    "recall_option",
    "purchase_contract",
    "release",
    "non_tender",
    "restricted_place",
    "restricted_activate",
    "foreign_place",
    "foreign_reinstate",
    "retirement",
    "death",
    "waiver_request_outright",
    "waiver_request_trade",
    "waiver_request_rule5",
    "extension",
}

FREE_AGENT_SIGNINGS = {"mlb_signing", "in_season_fa", "minor_signing", "ifa_signing"}

IL_ALREADY = {
    "il_7": "roster_7dayIL",
    "il_56": "roster_56dayIL",
    "il_eos": "roster_eosIL",
}

DISPOSING_KINDS = MUST_BE_ON_CLUB | {"trade"}


def evaluate(team, code, assets, contract_terms=None, proposal_id=None):
    """Return human-readable problems. An empty list means the filing can be stored."""
    problems = []
    players = [asset.get("player") for asset in assets if asset.get("player") is not None]
    problems.extend(_players_on_club(team, code, assets, players))
    problems.extend(_roster_state(team, code, players))
    problems.extend(_already_pending(team, code, players, proposal_id))
    problems.extend(_money(team, code, assets, contract_terms, proposal_id))
    problems.extend(_forty_man(team, code, assets, proposal_id))
    return problems


def assert_legal(team, code, assets, contract_terms=None, proposal_id=None):
    from npl.transactions.service import TransactionError

    problems = evaluate(team, code, assets, contract_terms=contract_terms, proposal_id=proposal_id)
    if problems:
        raise TransactionError(" ".join(problems))


def _players_on_club(team, code, assets, players):
    problems = []
    if code in FREE_AGENT_SIGNINGS:
        for player in players:
            if player.team_id:
                club = player.team.short_name if player.team_id else "another club"
                problems.append(f"{player.name} is already on {club}. A signing is for a free agent.")
    if code == "extension":
        for player in players:
            if player.team_id != team.id:
                problems.append(f"{player.name} is not under contract to {team.short_name}.")
    if code == "trade":
        for asset in assets:
            player = asset.get("player")
            if player is None:
                continue
            origin = asset.get("from_team") or team
            if player.team_id and player.team_id != origin.id:
                problems.append(f"{player.name} is not on {origin.short_name}.")
    if code in MUST_BE_ON_CLUB and code != "extension":
        if code in {"release", "non_tender", "retirement", "death", "option_minors", "recall_option", "purchase_contract"} and not players:
            problems.append("Name the player.")
        for player in players:
            if player.team_id != team.id:
                problems.append(f"{player.name} is not on {team.short_name}.")
    if code == "rule4_draft":
        for player in players:
            if player.team_id:
                problems.append(f"{player.name} is already on a club.")
    return problems


def _roster_state(team, code, players):
    problems = []
    for player in players:
        if player.team_id != team.id and code not in FREE_AGENT_SIGNINGS | {"trade", "rule4_draft", "rule5_draft"}:
            continue
        if code == "option_minors":
            if not player.roster_40man:
                problems.append(f"{player.name} is not on the 40-man, so he cannot be optioned.")
            elif _options_left(player) <= 0:
                problems.append(f"{player.name} has no options left.")
            elif player.roster_tripleA_option:
                problems.append(f"{player.name} is already on option.")
        elif code == "recall_option":
            if not player.roster_tripleA_option:
                problems.append(f"{player.name} is not on optional assignment.")
        elif code == "purchase_contract":
            if player.roster_40man:
                problems.append(f"{player.name} is already on the 40-man.")
        elif code in IL_ALREADY and getattr(player, IL_ALREADY[code], False):
            problems.append(f"{player.name} is already on that injured list.")
        elif code == "il_activate" and not _on_il(player):
            problems.append(f"{player.name} is not on an injured list.")
        elif code == "il_move" and not _on_il(player):
            problems.append(f"{player.name} is not on an injured list to move.")
        elif code in {"il_7", "il_56", "il_eos", "il_covid"} and not (
            player.roster_40man or _on_il(player)
        ):
            problems.append(f"{player.name} has to be on the 40-man or an injured list.")
        elif code == "restricted_activate" and not player.roster_restricted:
            problems.append(f"{player.name} is not on the restricted list.")
        elif code == "restricted_place" and player.roster_restricted:
            problems.append(f"{player.name} is already on the restricted list.")
        elif code == "foreign_reinstate" and not player.roster_foreign:
            problems.append(f"{player.name} is not on the foreign list.")
    return problems


def _already_pending(team, code, players, proposal_id):
    if code not in DISPOSING_KINDS or not players:
        return []
    wanted = {player.pk for player in players}
    problems = []
    for proposal in open_proposals():
        if proposal_id and proposal.id == proposal_id:
            continue
        if proposal.kind not in DISPOSING_KINDS and proposal.kind != "trade":
            continue
        for asset in proposal.assets.all():
            if asset.player_id not in wanted:
                continue
            if proposal.kind == "trade" and asset.from_team_id not in {None, team.id}:
                continue
            name = asset.player.name if asset.player_id else "That player"
            problems.append(
                f"{name} is already in proposal #{proposal.id} ({proposal.kind_label}), which has not been processed."
            )
            wanted.discard(asset.player_id)
    return problems


def _money(team, code, assets, contract_terms, proposal_id):
    pending = {"cash": 0, "cap": 0, "ifa": 0}
    for proposal in open_proposals():
        if proposal_id and proposal.id == proposal_id:
            continue
        for team_id, field, delta in money_moves(
            proposal.kind,
            proposal.originating_team,
            [
                {
                    "asset_type": asset.asset_type,
                    "player": asset.player,
                    "from_team": asset.from_team,
                    "to_team": asset.to_team,
                    "amount": asset.amount,
                    "contract_terms": asset.contract_terms,
                }
                for asset in proposal.assets.all()
            ],
            proposal.contract_terms,
        ):
            if team_id == team.id:
                pending[field] += delta
    incoming = {"cash": 0, "cap": 0, "ifa": 0}
    for team_id, field, delta in money_moves(code, team, assets, contract_terms):
        if team_id == team.id:
            incoming[field] += delta
    problems = []
    balances = {"cash": team.cash, "cap": team.cap_space, "ifa": team.ifa}
    names = {"cash": "cash", "cap": "cap space", "ifa": "IFA pool space"}
    for field, balance in balances.items():
        if balance is None:
            continue
        spend = pending[field] + incoming[field]
        if balance + spend < 0:
            problems.append(
                f"This would leave {team.short_name} ${abs(balance + spend):,} short of {names[field]} after other pending proposals."
            )
    return problems


def _forty_man(team, code, assets, proposal_id):
    if code not in FORTY_MAN_ADDS | FORTY_MAN_DROPS | {"trade"}:
        return []
    current = models.Player.objects.filter(team=team, roster_40man=True).count()
    pending = 0
    for proposal in open_proposals():
        if proposal_id and proposal.id == proposal_id:
            continue
        if proposal.originating_team_id != team.id and proposal.kind != "trade":
            continue
        pending += forty_man_delta(
            proposal.kind,
            team,
            [
                {
                    "asset_type": asset.asset_type,
                    "player": asset.player,
                    "from_team": asset.from_team,
                    "to_team": asset.to_team,
                }
                for asset in proposal.assets.all()
            ],
        )
    net = current + pending + forty_man_delta(code, team, assets)
    if net > 40:
        return [f"This would put {team.short_name} at {net} players on the 40-man. The limit is 40."]
    return []


def _options_left(player):
    if player.options is None or player.options >= 99:
        return 0
    return player.options


def _on_il(player):
    return bool(player.roster_7dayIL or player.roster_56dayIL or player.roster_eosIL)
