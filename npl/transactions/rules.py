"""Reject filings that the roster, the books, or the published rules cannot support.

Directors still judge close calls. These checks stop filings that are already
false, and filings that miss a rule in section 8 of the NPL Rules. Each of
those messages names the section.
"""

import re

from django.utils import timezone

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


def evaluate(team, code, assets, contract_terms=None, proposal_id=None, effective_date=None):
    """Return human-readable problems. An empty list means the filing can be stored."""
    problems = []
    players = [asset.get("player") for asset in assets if asset.get("player") is not None]
    on_date = effective_date or timezone.localdate()
    problems.extend(_players_on_club(team, code, assets, players))
    problems.extend(_roster_state(team, code, players))
    problems.extend(_published_rules(team, code, assets, players, on_date))
    problems.extend(_already_pending(team, code, players, proposal_id))
    problems.extend(_money(team, code, assets, contract_terms, proposal_id))
    problems.extend(_forty_man(team, code, assets, proposal_id))
    if code == "trade":
        for club in _trade_clubs(team, assets):
            if club.pk == team.pk:
                continue
            leaving = [
                asset.get("player")
                for asset in assets
                if asset.get("player") is not None
                and asset.get("from_team") is not None
                and asset["from_team"].pk == club.pk
            ]
            problems.extend(_already_pending(club, code, leaving, proposal_id))
            problems.extend(_money(club, code, assets, contract_terms, proposal_id))
            problems.extend(_forty_man(club, code, assets, proposal_id))
    return problems


def _trade_clubs(team, assets):
    clubs = {team.pk: team}
    for asset in assets:
        for key in ("from_team", "to_team"):
            club = asset.get(key)
            if club is not None:
                clubs[club.pk] = club
    return list(clubs.values())


def assert_legal(team, code, assets, contract_terms=None, proposal_id=None, effective_date=None):
    from npl.transactions.service import TransactionError

    problems = evaluate(
        team,
        code,
        assets,
        contract_terms=contract_terms,
        proposal_id=proposal_id,
        effective_date=effective_date,
    )
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
                problems.append(
                    f"{player.name} is not on the 40-man, so he cannot be optioned. NPL Rules 8.3.1."
                )
            elif player.options is not None and player.options >= 99:
                problems.append(
                    f"{player.name} is a veteran and cannot be optioned. The only assignment to the minors is outright waivers. NPL Rules 8.3.3."
                )
            elif _options_left(player) <= 0 and _on_active_roster(player):
                problems.append(
                    f"{player.name} has no options left and is on the active roster. The only assignment to the minors is outright waivers. NPL Rules 8.3.3."
                )
            elif player.roster_tripleA_option:
                problems.append(f"{player.name} is already on option. NPL Rules 8.3.1.")
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
                cite = {"cash": " NPL Rules 8.7.5.1.", "ifa": " NPL Rules 8.7.4.", "cap": ""}.get(field, "")
                problems.append(
                    f"This would leave {team.short_name} ${abs(balance + spend):,} short of {names[field]} after other pending proposals.{cite}"
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


def _on_active_roster(player):
    """On the active major-league roster, rather than already in the minors."""
    if not player.roster_40man:
        return False
    return not (
        player.roster_tripleA
        or player.roster_tripleA_option
        or player.roster_doubleA
        or player.roster_singleA
        or player.roster_nonroster
    )


def _major_league_contract(player):
    """A player who cannot be dealt after the July 31 deadline. NPL Rules 8.7.2."""
    if player.roster_foreign or player.roster_retired:
        return False
    if player.roster_doubleA or player.roster_singleA or player.roster_nonroster:
        return False
    if player.roster_tripleA and not player.roster_40man and not player.roster_tripleA_option:
        return False
    return bool(
        player.roster_40man
        or player.roster_tripleA_option
        or player.roster_outrighted
        or _on_il(player)
    )


def _published_rules(team, code, assets, players, on_date):
    """Section 8 checks that do not depend on a director's judgment."""
    problems = []
    problems.extend(_calendar_rules(code, players, on_date))
    problems.extend(_trade_asset_rules(assets, on_date))
    if code == "il_56":
        count = models.Player.objects.filter(team=team, roster_40man=True).count()
        if count != 40:
            problems.append(
                f"A player may not be placed on the 56-day IL unless the 40-man contains 40 players. {team.short_name} has {count}. NPL Rules 8.2.1."
            )
    if code == "il_activate":
        for player in players:
            if player.roster_eosIL and on_date.month in range(3, 10):
                problems.append(
                    f"{player.name} is on the end-of-season IL and cannot be activated for the rest of the season. NPL Rules 8.2.1."
                )
    if code == "waiver_request_outright":
        for player in players:
            if not player.roster_40man:
                problems.append(
                    f"{player.name} is not on the 40-man. Outright waivers remove a player from the 40-man. NPL Rules 8.8.2.1."
                )
    if code == "foreign_place":
        for player in players:
            if not _major_league_contract(player):
                problems.append(
                    f"{player.name} is on a minor-league contract. He stays on the 85-man unless he is released. NPL Rules 8.1.2."
                )
    if code == "option_minors":
        for player in players:
            if _on_il(player):
                problems.append(
                    f"{player.name} is on the injured list and cannot be sent to the minors. NPL Rules 8.2."
                )
    if code == "rule5_draft":
        forty = models.Player.objects.filter(team=team, roster_40man=True).count()
        if forty >= 40:
            problems.append(
                f"{team.short_name} has a full 40-man and cannot make a Rule 5 selection. NPL Rules 8.6.4."
            )
        rostered = models.Player.objects.filter(team=team).count()
        if rostered >= 85:
            problems.append(
                f"{team.short_name} has a full 85-man and cannot make a Rule 5 selection. NPL Rules 8.6.4."
            )
    if code == "trade":
        for asset in assets:
            if asset.get("asset_type") != "carried_salary":
                continue
            giver = asset.get("from_team") or team
            amount = asset.get("amount") or 0
            if giver.carried_salary is not None and amount > giver.carried_salary:
                problems.append(
                    f"{giver.short_name} does not have ${amount:,} of carried salary on the books. NPL Rules 8.7.5.2.4."
                )
    return problems


def _calendar_rules(code, players, on_date):
    problems = []
    il_placement = {"il_7", "il_56", "il_eos", "il_covid", "il_move"}
    if code in il_placement and on_date.month in {10, 11, 12, 1, 2}:
        problems.append(
            "There is no injured list in the offseason. Placement begins in March. NPL Rules 8.2."
        )
    if code == "option_minors" and on_date.month in {9, 10, 11, 12, 1, 2}:
        problems.append(
            "Players may not be optioned in September or the offseason. NPL Rules 8.3.2.1."
        )
    if code == "non_tender" and on_date.month in range(4, 10):
        problems.append("Players can be nontendered in the offseason only. NPL Rules 8.4.2.")
    if code == "trade" and on_date.month in {8, 9}:
        for player in players:
            if _major_league_contract(player):
                problems.append(
                    f"{player.name} is on a major-league contract and cannot be traded after the July 31 deadline. NPL Rules 8.7.2."
                )
    return problems


def _trade_asset_rules(assets, on_date):
    problems = []
    for asset in assets:
        kind = asset.get("asset_type")
        if kind == "cap_space":
            problems.append(
                "Cap space itself cannot be traded. A trade may include cash, carried salary, or IFA cap space. NPL Rules 8.7.1."
            )
        label = asset.get("raw_label") or ""
        if kind == "draft_pick":
            years = [int(year) for year in re.findall(r"20\d{2}", label)]
            if any(year >= on_date.year + 2 for year in years):
                problems.append(
                    f"Only picks for the next upcoming draft may be dealt. NPL Rules 8.7.1. ({label})"
                )
        player = asset.get("player")
        if kind == "future_considerations" and player is not None and player.roster_40man:
            problems.append(
                f"{player.name} is on the 40-man. A player to be named later cannot be on the 40-man. NPL Rules 8.7.1."
            )
    return problems
