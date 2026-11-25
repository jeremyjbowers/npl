"""How a filing reads on the review page.

A director approves dozens of these a week. The headline is the club,
the move, and the player's major-league team. Impact follows, including
whether the roster checks passed.
"""

from npl.transactions.catalog import (
    ASSET_CAP,
    ASSET_CASH,
    ASSET_COVERAGE,
    ASSET_DRAFT_PICK,
    ASSET_FUTURE,
    ASSET_IFA,
    ASSET_PLAYER,
    ASSET_CARRIED_SALARY,
)

# The word in front of the player's name. Kept short so the headline scans.
VERBS = {
    "il_7": "7-day IL",
    "il_56": "56-day IL",
    "il_eos": "end-of-season IL",
    "il_covid": "COVID IL",
    "il_move": "IL move",
    "il_activate": "activate from the IL",
    "in_limbo": "limbo assignment",
    "option_minors": "option",
    "recall_option": "recall",
    "purchase_contract": "purchase",
    "release": "release",
    "non_tender": "nontender",
    "restricted_place": "restricted list",
    "restricted_activate": "activate from the restricted list",
    "foreign_place": "foreign list",
    "foreign_reinstate": "reinstate",
    "retirement": "retire",
    "death": "death of",
    "mlb_signing": "sign",
    "in_season_fa": "sign",
    "minor_signing": "minor-league signing",
    "ifa_signing": "IFA signing",
    "extension": "extend",
    "exercise_option": "exercise option",
    "exercise_vesting_option": "exercise vesting option",
    "decline_option": "decline option",
    "qualifying_offer": "qualifying offer",
    "contract_amnesty": "amnesty",
    "waiver_request_outright": "outright waivers",
    "waiver_request_trade": "trade waivers",
    "waiver_cleared_outright": "cleared waivers",
    "waiver_claimed": "claim",
    "waiver_request_rule5": "Rule 5 waivers",
    "waiver_returned_rule5": "Rule 5 return",
    "rule5_draft": "Rule 5 draft",
    "rule4_draft": "Rule 4 draft",
    "auction_result": "auction",
    "trade": "trade",
}

_MONEY = {
    ASSET_CASH: "cash",
    ASSET_CAP: "cap space",
    ASSET_IFA: "IFA pool space",
    ASSET_CARRIED_SALARY: "carried salary",
    ASSET_COVERAGE: "salary coverage",
}


def filing_headline(proposal):
    """The sentence at the top of the review page, plus whether the body adds more."""
    pieces = [_piece(asset, proposal) for asset in proposal.assets.all()]
    verb = VERBS.get(proposal.kind) or (proposal.kind_label or proposal.kind or "filing").lower()
    club = proposal.originating_team
    club_name = _club_name(club)
    named = _english_join([_plain(piece) for piece in pieces])
    action = f"{verb} {named}".strip()
    body = f"{club_name} {action}".strip() if club_name else action
    return {
        "verb": verb,
        "club": club,
        "club_name": club_name,
        "pieces": pieces,
        "text": f"proposal {proposal.id}: {body}",
        "show_pieces": _show_pieces(proposal, pieces),
    }


def review_flags(proposal):
    """Checks that still fail. Empty means the filing passed and can be approved."""
    from npl.transactions.rules import evaluate

    assets = [
        {
            "asset_type": asset.asset_type,
            "player": asset.player,
            "from_team": asset.from_team,
            "to_team": asset.to_team,
            "amount": asset.amount,
            "contract_terms": asset.contract_terms,
            "raw_label": asset.raw_label,
            "notes": asset.notes,
        }
        for asset in proposal.assets.all()
    ]
    flags = evaluate(
        proposal.originating_team,
        proposal.kind,
        assets,
        contract_terms=proposal.contract_terms,
        proposal_id=proposal.pk,
        effective_date=proposal.effective_date,
        notes=proposal.notes or "",
    )
    flags = list(flags)
    if proposal.flagged:
        note = (proposal.flag_note or "").strip()
        flags.append(f"Flagged as improper. {note}".strip())
    for party in proposal.parties.all():
        if party.agreement_status != "pending" or not party.team_id:
            continue
        name = party.team.short_name or party.team.abbreviation or "A club"
        flags.append(f"{name} has not agreed.")
    return flags


def _show_pieces(proposal, pieces):
    """A one-player move is already the headline. Trades and terms need the body."""
    if proposal.kind == "trade":
        return True
    assets = list(proposal.assets.all())
    if len(assets) != 1 or not pieces or pieces[0].get("player") is None:
        return True
    asset = assets[0]
    if asset.amount or asset.contract_terms or proposal.contract_terms:
        return True
    if pieces[0].get("suffix"):
        return True
    return False


def _piece(asset, proposal):
    if asset.asset_type == ASSET_PLAYER and asset.player_id and asset.player is not None:
        return _player_piece(asset, proposal)
    return {
        "player": None,
        "label": _other_label(asset),
        "position": "",
        "mlb": "",
        "suffix": _route(asset),
    }


def _player_piece(asset, proposal):
    player = asset.player
    filing = _club_name(proposal.originating_team)
    origin = _club_name(asset.from_team)
    dest = _club_name(asset.to_team)
    route = []
    if origin and origin != filing:
        route.append(f"from {origin}")
    if dest and dest != filing:
        route.append(f"to {dest}")
    return {
        "player": player,
        "label": player.name,
        "position": (player.position or "").strip(),
        "mlb": (player.mlb_org or "").strip(),
        "suffix": " ".join(route),
    }


def _other_label(asset):
    if asset.asset_type == ASSET_DRAFT_PICK:
        return asset.raw_label or "a draft pick"
    if asset.asset_type == ASSET_FUTURE:
        return asset.raw_label or "a player to be named later"
    if asset.asset_type == ASSET_PLAYER:
        return asset.raw_label or "a player"
    kind = _MONEY.get(asset.asset_type)
    if kind and asset.amount:
        return f"${int(asset.amount):,} {kind}"
    if asset.raw_label:
        return asset.raw_label
    return kind or asset.asset_type or "an asset"


def _route(asset):
    origin = _club_name(asset.from_team)
    dest = _club_name(asset.to_team)
    if origin and dest:
        return f"from {origin} to {dest}"
    if dest:
        return f"to {dest}"
    if origin:
        return f"from {origin}"
    return ""


def _club_name(team):
    if team is None:
        return ""
    return (team.short_name or team.abbreviation or "").strip()


def _plain(piece):
    text = piece["label"]
    paren = [bit for bit in (piece.get("position") or "", piece.get("mlb") or "") if bit]
    if paren:
        text += " (" + ", ".join(paren) + ")"
    if piece["suffix"]:
        text += " " + piece["suffix"]
    return text


def _english_join(parts):
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]
