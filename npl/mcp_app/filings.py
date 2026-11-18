"""Club filings for the MCP server.

A read-write key acts as its owner. The filing is a proposal: the player
stays put until the league office posts it. Draft selections and auction
bids are refused before they reach the transaction service.
"""

from __future__ import annotations

import datetime

from npl import models
from npl.mcp_app.context import get_current_token
from npl.transactions import service
from npl.transactions.catalog import CLUB_FILING_REFUSAL, club_can_file, fileable_kinds


def proposal_body(
    *,
    code,
    team=None,
    player=None,
    counterparty=None,
    counterparty_teams=None,
    assets=None,
    notes="",
    effective_date=None,
    contract_terms=None,
    veteran_disposition="",
    amount=None,
):
    """JSON body for POST /api/v1/transactions/proposals/."""
    if not club_can_file(code):
        raise service.TransactionError(CLUB_FILING_REFUSAL)
    body = {
        "code": code,
        "notes": notes or "",
        "veteran_disposition": veteran_disposition or "",
    }
    if team not in (None, ""):
        body["team"] = team
    if counterparty not in (None, ""):
        body["counterparty_team"] = counterparty
    if counterparty_teams:
        body["counterparty_teams"] = list(counterparty_teams)
    if effective_date:
        body["effective_date"] = effective_date
    if contract_terms:
        body["contract_terms"] = contract_terms
    pieces = list(assets or [])
    if not pieces and player not in (None, ""):
        asset = {"asset_type": "player", "player": str(player)}
        if amount is not None:
            asset["amount"] = amount
        pieces = [asset]
    if pieces:
        body["assets"] = pieces
    return body


def _user():
    token = get_current_token()
    if token is None or not token.user_id:
        raise service.TransactionError("MCP call is not authenticated.")
    return token.user


def _writer():
    token = get_current_token()
    if token is None or not token.allows_write:
        raise service.TransactionError(
            "This API key is read-only. Filing a transaction needs a read-write key."
        )
    return token.user


def _date(value):
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _caught(fn):
    try:
        return fn()
    except (
        service.TransactionError,
        KeyError,
        ValueError,
        models.Team.DoesNotExist,
        models.Player.DoesNotExist,
    ) as exc:
        return {"error": str(exc)}


def list_transaction_kinds():
    return {"kinds": fileable_kinds()}


def list_transaction_proposals():
    def run():
        user = _user()
        rows = [service.proposal_to_dict(item) for item in service.visible_proposals(user)]
        return {"proposals": rows}

    return _caught(run)


def get_transaction_proposal(proposal_id):
    def run():
        user = _user()
        proposal = service.visible_proposals(user).filter(pk=proposal_id).first()
        if proposal is None:
            return {"error": "Proposal not found."}
        return service.proposal_to_dict(proposal)

    return _caught(run)


def create_transaction_proposal(**kwargs):
    def run():
        user = _writer()
        body = proposal_body(**kwargs)
        proposal = service.create_proposal(
            user=user,
            team=body.get("team"),
            code=body["code"],
            assets=body.get("assets") or [],
            counterparty_team=body.get("counterparty_team"),
            counterparty_teams=body.get("counterparty_teams"),
            notes=body.get("notes") or "",
            source=models.TransactionProposal.API,
            effective_date=_date(body.get("effective_date")),
            contract_terms=body.get("contract_terms"),
            veteran_disposition=body.get("veteran_disposition") or "",
        )
        return service.proposal_to_dict(proposal)

    return _caught(run)


def _respond(fn, proposal_id):
    def run():
        user = _writer()
        proposal = models.TransactionProposal.objects.filter(pk=proposal_id).first()
        if proposal is None:
            return {"error": "Proposal not found."}
        return service.proposal_to_dict(fn(user, proposal))

    return _caught(run)


def agree_transaction(proposal_id):
    return _respond(service.agree, proposal_id)


def decline_transaction(proposal_id):
    return _respond(service.decline, proposal_id)


def withdraw_transaction(proposal_id):
    return _respond(service.withdraw, proposal_id)


def list_open_waivers():
    def run():
        _user()
        return {"waivers": service.open_waivers()}

    return _caught(run)


def claim_waiver(waiver_id, notes="", team=None):
    def run():
        user = _writer()
        waiver = models.Waiver.objects.filter(pk=waiver_id).first()
        if waiver is None:
            return {"error": "Waiver not found."}
        claim = service.claim_waiver(user, waiver, notes=notes or "", team=team)
        return {
            "id": claim.id,
            "waiver_id": waiver.id,
            "team": claim.team.abbreviation if claim.team_id else None,
            "status": waiver.status,
        }

    return _caught(run)
