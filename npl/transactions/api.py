"""JSON API for transaction proposals, waivers, and drafts."""

import datetime
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from npl import models
from npl.api_tokens import authenticate, mark_used
from npl.transactions import service
from npl.transactions.mcp import tool_manifest

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def _body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return request.POST


def _auth(request):
    """Accept a bearer token, or a signed-in session.

    A bearer token acts as its owner. Read tokens can use GET. Read-write
    tokens can also submit and respond. An invalid token is rejected even
    when a session cookie is also present.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header:
        scheme, _, raw = header.partition(" ")
        if scheme.lower() != "bearer" or not raw.strip():
            return JsonResponse({"error": "Send Authorization: Bearer <token>."}, status=401)
        token = authenticate(raw.strip())
        if token is None:
            return JsonResponse({"error": "Invalid or revoked token."}, status=401)
        if request.method not in _READ_METHODS and token.scope != models.ApiToken.READ_WRITE:
            return JsonResponse({"error": "This token is read-only."}, status=403)
        request.user = token.user
        request.api_token = token
        mark_used(token)
        return None
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in or send a bearer token."}, status=401)
    return None


def _date(value):
    if not value:
        return None
    return datetime.date.fromisoformat(value)


@csrf_exempt
def kinds(request):
    denied = _auth(request)
    if denied:
        return denied
    return JsonResponse({"kinds": service.list_kinds()})


@csrf_exempt
def proposals(request):
    denied = _auth(request)
    if denied:
        return denied
    if request.method == "GET":
        payload = [service.proposal_to_dict(item) for item in service.visible_proposals(request.user)]
        return JsonResponse({"proposals": payload})
    if request.method != "POST":
        return JsonResponse({"error": "Use GET or POST."}, status=405)
    data = _body(request)
    source = data.get("source") or models.TransactionProposal.API
    if source not in {choice for choice, _label in models.TransactionProposal.SOURCE_CHOICES}:
        source = models.TransactionProposal.API
    try:
        proposal = service.create_proposal(
            user=request.user,
            team=data.get("team"),
            code=data.get("code"),
            assets=data.get("assets") or [],
            counterparty_team=data.get("counterparty_team"),
            notes=data.get("notes") or "",
            source=source,
            effective_date=_date(data.get("effective_date")),
            contract_terms=data.get("contract_terms"),
            veteran_disposition=data.get("veteran_disposition") or "",
        )
    except service.TransactionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except (KeyError, ValueError, models.Team.DoesNotExist, models.Player.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(service.proposal_to_dict(proposal), status=201)


@csrf_exempt
def proposal_detail(request, proposal_id):
    denied = _auth(request)
    if denied:
        return denied
    proposal = service.visible_proposals(request.user).filter(pk=proposal_id).first()
    if proposal is None:
        return JsonResponse({"error": "Proposal not found."}, status=404)
    return JsonResponse(service.proposal_to_dict(proposal))


def _action(request, proposal_id, fn):
    denied = _auth(request)
    if denied:
        return denied
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    proposal = models.TransactionProposal.objects.filter(pk=proposal_id).first()
    if proposal is None:
        return JsonResponse({"error": "Proposal not found."}, status=404)
    try:
        proposal = fn(request.user, proposal)
    except service.TransactionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(service.proposal_to_dict(proposal))


@csrf_exempt
def proposal_agree(request, proposal_id):
    return _action(request, proposal_id, service.agree)


@csrf_exempt
def proposal_decline(request, proposal_id):
    return _action(request, proposal_id, service.decline)


@csrf_exempt
def proposal_withdraw(request, proposal_id):
    return _action(request, proposal_id, service.withdraw)


@csrf_exempt
def waiver_claim(request, waiver_id):
    denied = _auth(request)
    if denied:
        return denied
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    waiver = models.Waiver.objects.filter(pk=waiver_id).first()
    if waiver is None:
        return JsonResponse({"error": "Waiver not found."}, status=404)
    data = _body(request)
    try:
        claim = service.claim_waiver(request.user, waiver, notes=data.get("notes") or "")
    except service.TransactionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {"id": claim.id, "waiver_id": waiver.id, "team_id": claim.team_id, "status": waiver.status},
        status=201,
    )


@csrf_exempt
def drafts(request):
    denied = _auth(request)
    if denied:
        return denied
    payload = []
    for session in models.DraftSession.objects.select_related("current_pick"):
        pick = session.current_pick
        payload.append(
            {
                "id": session.id,
                "year": session.year,
                "half": session.half,
                "draft_type": session.draft_type,
                "status": session.status,
                "selection_fee": session.selection_fee,
                "current_pick_id": pick.id if pick else None,
                "current_team_id": pick.team_id if pick else None,
            }
        )
    return JsonResponse({"drafts": payload})


@csrf_exempt
def draft_pick(request, session_id):
    denied = _auth(request)
    if denied:
        return denied
    if request.method != "POST":
        return JsonResponse({"error": "Use POST."}, status=405)
    session = models.DraftSession.objects.filter(pk=session_id).first()
    if session is None:
        return JsonResponse({"error": "Draft not found."}, status=404)
    data = _body(request)
    try:
        proposal = service.submit_draft_pick(request.user, session, data.get("player"))
    except service.TransactionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(service.proposal_to_dict(proposal), status=201)


@csrf_exempt
def mcp_tools(request):
    denied = _auth(request)
    if denied:
        return denied
    return JsonResponse(
        {
            "auth": {
                "type": "bearer",
                "header": "Authorization",
                "scopes": [
                    {"scope": models.ApiToken.READ, "methods": ["GET"]},
                    {"scope": models.ApiToken.READ_WRITE, "methods": ["GET", "POST"]},
                ],
            },
            "tools": tool_manifest(),
        }
    )
