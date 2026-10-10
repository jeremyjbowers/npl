"""Create and resolve transaction proposals.

Web forms, the JSON API, and MCP tools all call these functions.
Executing a proposal writes the historical Transaction ledger. It does not
move players, contracts, or draft picks; directors still apply roster effects.
"""

import datetime
from decimal import Decimal

from django.utils import timezone

from npl import models
from npl.transactions.catalog import (
    ASSET_CASH,
    ASSET_DRAFT_PICK,
    ASSET_FUTURE,
    ASSET_IFA,
    ASSET_PLAYER,
    ASSET_TYPES,
    FOREIGN_FORM_TO_CODE,
    FORM_TYPE_TO_CODE,
    IL_FORM_TO_CODE,
    KINDS,
    OFFSEASON_FORM_TO_CODE,
    SIGNING_CODES,
    WAIVER_FORM_TO_CODE,
    get_kind,
    rl_rules,
    sheet_asset_qualifier,
    sheet_asset_type,
)


class TransactionError(Exception):
    pass


def teams_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return models.Team.objects.none()
    try:
        owner = user.owner
    except models.Owner.DoesNotExist:
        return models.Team.objects.none()
    return models.Team.objects.filter(owners=owner)


def _require_team(user, team):
    if team is None:
        raise TransactionError("Choose a team.")
    if not teams_for_user(user).filter(pk=team.pk).exists() and not getattr(user, "is_staff", False):
        raise TransactionError("You can only submit transactions for a team you own.")
    if hasattr(team, "can_transact") and not team.can_transact:
        raise TransactionError("This team is frozen until league fees are paid.")
    return team


def _resolve_team(value):
    if value is None or value == "":
        return None
    if isinstance(value, models.Team):
        return value
    return models.Team.objects.get(pk=int(value))


def _resolve_player(value):
    if value is None or value == "":
        return None
    if isinstance(value, models.Player):
        return value
    return models.Player.objects.get(mlb_id=str(value))


def next_processing_week(on_date=None):
    on_date = on_date or timezone.localdate()
    days_ahead = (7 - on_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return on_date + datetime.timedelta(days=days_ahead)


def transaction_type_for(code):
    kind = get_kind(code)
    obj, _created = models.TransactionType.objects.get_or_create(
        code=code,
        defaults={
            "transaction_type": kind["label"],
            "category": kind["category"],
            "requires_agreement": kind["requires_agreement"],
            "requires_contract": kind["requires_contract"],
        },
    )
    return obj


def _terms_present(terms):
    if not terms:
        return False
    if not isinstance(terms, dict):
        return True
    return any(value not in (None, "", []) for value in terms.values())


def _normalize_asset(raw, originating_team, counterparty):
    if not isinstance(raw, dict):
        raise TransactionError("Each asset must be an object.")
    asset_type = raw.get("asset_type") or sheet_asset_type(raw.get("raw_label")) or ASSET_PLAYER
    if asset_type not in ASSET_TYPES:
        raise TransactionError(f"Unknown asset type: {asset_type}")
    player = _resolve_player(raw.get("player"))
    if player is None and raw.get("mlb_id"):
        player = models.Player.objects.filter(mlb_id=str(raw["mlb_id"])).first()
    draft_pick = raw.get("draft_pick")
    if draft_pick is not None and not isinstance(draft_pick, models.DraftPick):
        draft_pick = models.DraftPick.objects.filter(pk=draft_pick).first()
    from_team = _resolve_team(raw.get("from_team")) if raw.get("from_team") else originating_team
    to_team = _resolve_team(raw.get("to_team")) if raw.get("to_team") else counterparty
    amount = raw.get("amount")
    if amount in ("", None):
        amount = None
    else:
        amount = int(amount)
    return {
        "asset_type": asset_type,
        "player": player,
        "draft_pick": draft_pick,
        "from_team": from_team,
        "to_team": to_team,
        "mlb_id": raw.get("mlb_id") or (player.mlb_id if player else None),
        "scoresheet_id": raw.get("scoresheet_id") or None,
        "raw_label": raw.get("raw_label") or (player.name if player else None),
        "qualifier": raw.get("qualifier") or sheet_asset_qualifier(raw.get("raw_label")) or "",
        "amount": amount,
        "contract_terms": raw.get("contract_terms") or None,
        "notes": raw.get("notes") or "",
    }


def create_proposal(
    *,
    user,
    team,
    code,
    assets=None,
    counterparty_team=None,
    notes="",
    source="web",
    effective_date=None,
    contract_terms=None,
    waiver_type=None,
    veteran_disposition="",
    service_class="",
    rl_type="",
    limbo_reason="",
):
    kind = get_kind(code)
    team = _require_team(user, _resolve_team(team))
    counterparty = _resolve_team(counterparty_team) if counterparty_team else None
    if kind["requires_agreement"] and counterparty is None:
        raise TransactionError("A trade needs the other team.")
    if counterparty and counterparty.pk == team.pk:
        raise TransactionError("The other team has to be a different club.")

    normalized = [
        _normalize_asset(asset, team, counterparty) for asset in (assets or [])
    ]
    if code == "trade" and not normalized:
        raise TransactionError("A trade needs at least one player, pick, or financial asset.")
    if code in SIGNING_CODES:
        has_player = any(asset["player"] or asset["raw_label"] for asset in normalized)
        has_money = _terms_present(contract_terms) or any(
            asset["amount"] is not None or _terms_present(asset["contract_terms"])
            for asset in normalized
        )
        if not has_player or not has_money:
            raise TransactionError("A signing needs a player and contract terms or an amount.")
    if code.startswith("waiver_request") or waiver_type:
        players = [asset["player"] for asset in normalized if asset["player"]]
        if not players or any(player.team_id != team.id for player in players):
            raise TransactionError("A waiver request needs a player on your team.")
    if code == "in_limbo":
        limbo_players = [asset["player"] for asset in normalized if asset["player"]]
        if not limbo_players:
            raise TransactionError("An in-limbo assignment needs a player on your team.")

    if kind["requires_agreement"]:
        status = models.TransactionProposal.AWAITING
    else:
        status = models.TransactionProposal.PROPOSED

    proposal = models.TransactionProposal.objects.create(
        kind=code,
        transaction_type=transaction_type_for(code),
        status=status,
        submitted_by=user if getattr(user, "is_authenticated", False) else None,
        originating_team=team,
        effective_date=effective_date,
        processing_week=next_processing_week(),
        notes=notes or "",
        source=source,
        contract_terms=contract_terms,
    )
    models.TransactionParty.objects.create(
        proposal=proposal,
        team=team,
        role=models.TransactionParty.ORIGINATOR,
        agreement_status=models.TransactionParty.ACCEPTED,
        agreed_by=user if getattr(user, "is_authenticated", False) else None,
        agreed_at=timezone.now(),
    )
    if counterparty:
        models.TransactionParty.objects.create(
            proposal=proposal,
            team=counterparty,
            role=models.TransactionParty.COUNTERPARTY,
            agreement_status=models.TransactionParty.PENDING,
        )
    for asset in normalized:
        models.TransactionAsset.objects.create(proposal=proposal, **asset)

    if code.startswith("waiver_request") or waiver_type:
        player = next((asset["player"] for asset in normalized if asset["player"]), None)
        placed = effective_date or timezone.localdate()
        models.Waiver.objects.create(
            proposal=proposal,
            player=player,
            placing_team=team,
            waiver_type=waiver_type or _waiver_type_for(code),
            status=models.Waiver.OPEN,
            salary=next((asset["amount"] for asset in normalized if asset["amount"]), None),
            mls_snapshot=(player.mls_time if player else "") or "",
            options_remaining=player.options if player else None,
            veteran_disposition=veteran_disposition or "",
            service_class=service_class or "",
            placed_on=placed,
            opens=timezone.now(),
        )
    if code == "in_limbo":
        player = next((asset["player"] for asset in normalized if asset["player"]), None)
        placed = effective_date or timezone.localdate()
        models.InLimboAssignment.objects.create(
            proposal=proposal,
            player=player,
            team=team,
            placed_on=placed,
            deadline=placed + datetime.timedelta(days=7),
            reason=limbo_reason or "",
            notes=notes or "",
        )
    if code == "restricted_place":
        player = next((asset["player"] for asset in normalized if asset["player"]), None)
        if player:
            rules = rl_rules(rl_type)
            models.RestrictedListStint.objects.create(
                proposal=proposal,
                player=player,
                team=team,
                rl_type=rl_type or "",
                counts_against_40=rules.get("counts_against_40", False),
                accrues_service=rules.get("accrues_service", False),
                accrues_salary=rules.get("accrues_salary", False),
                placed_on=effective_date or timezone.localdate(),
                notes=notes or "",
            )
    return proposal


def _waiver_type_for(code):
    return {
        "waiver_request_outright": models.Waiver.OUTRIGHT,
        "waiver_request_trade": models.Waiver.TRADE,
        "waiver_request_rule5": models.Waiver.RULE5,
    }.get(code, models.Waiver.OUTRIGHT)


def _party_for_user(proposal, user, role=None):
    teams = teams_for_user(user)
    parties = proposal.parties.filter(team__in=teams)
    if role:
        parties = parties.filter(role=role)
    party = parties.first()
    if party is None and not getattr(user, "is_staff", False):
        raise TransactionError("This proposal is for another team.")
    return party


def agree(user, proposal):
    if proposal.status != models.TransactionProposal.AWAITING:
        raise TransactionError("This proposal is not waiting on an agreement.")
    party = proposal.parties.filter(
        team__in=teams_for_user(user),
        role=models.TransactionParty.COUNTERPARTY,
        agreement_status=models.TransactionParty.PENDING,
    ).first()
    if party is None:
        raise TransactionError("Your team does not have a pending agreement on this proposal.")
    party.agreement_status = models.TransactionParty.ACCEPTED
    party.agreed_by = user
    party.agreed_at = timezone.now()
    party.save()
    if not proposal.parties.filter(agreement_status=models.TransactionParty.PENDING).exists():
        proposal.status = models.TransactionProposal.AGREED
        proposal.save(update_fields=["status", "last_modified"])
    return proposal


def decline(user, proposal):
    party = proposal.parties.filter(
        team__in=teams_for_user(user),
        role=models.TransactionParty.COUNTERPARTY,
        agreement_status=models.TransactionParty.PENDING,
    ).first()
    if party is None:
        raise TransactionError("Your team cannot decline this proposal.")
    party.agreement_status = models.TransactionParty.DECLINED
    party.agreed_by = user
    party.agreed_at = timezone.now()
    party.save()
    proposal.status = models.TransactionProposal.REJECTED
    proposal.save(update_fields=["status", "last_modified"])
    return proposal


def withdraw(user, proposal):
    if proposal.status not in (
        models.TransactionProposal.PROPOSED,
        models.TransactionProposal.AWAITING,
        models.TransactionProposal.DRAFT,
        models.TransactionProposal.AGREED,
    ):
        raise TransactionError("This proposal can no longer be withdrawn.")
    _party_for_user(proposal, user, role=models.TransactionParty.ORIGINATOR)
    proposal.status = models.TransactionProposal.WITHDRAWN
    proposal.save(update_fields=["status", "last_modified"])
    waiver = getattr(proposal, "waiver", None)
    if waiver and waiver.status == models.Waiver.OPEN:
        waiver.status = models.Waiver.WITHDRAWN
        waiver.save(update_fields=["status", "last_modified"])
    return proposal


def execute_proposal(user, proposal):
    if not getattr(user, "is_staff", False):
        raise TransactionError("Only directors can post a proposal to the transaction ledger.")
    if proposal.status == models.TransactionProposal.EXECUTED:
        raise TransactionError("This proposal is already on the ledger.")
    if proposal.status in (
        models.TransactionProposal.REJECTED,
        models.TransactionProposal.WITHDRAWN,
        models.TransactionProposal.VOIDED,
    ):
        raise TransactionError("This proposal is closed.")
    if proposal.parties.filter(agreement_status=models.TransactionParty.PENDING).exists():
        raise TransactionError("Every club in the trade still needs to agree.")

    txn_type = proposal.transaction_type or transaction_type_for(proposal.kind)
    when = proposal.effective_date or timezone.localdate()
    for asset in proposal.assets.all():
        player_label = asset.raw_label
        if asset.player:
            player_label = asset.player.name
        elif asset.asset_type == ASSET_CASH:
            player_label = player_label or "Cash Reserves"
        elif asset.asset_type == ASSET_IFA:
            player_label = player_label or "IFA Cap Space"
        elif asset.asset_type == ASSET_DRAFT_PICK:
            player_label = player_label or "Draft Pick"
        elif asset.asset_type == ASSET_FUTURE:
            player_label = player_label or "Future Considerations"
        ledger = models.Transaction.objects.create(
            date=when,
            player=asset.player,
            mlb_id=asset.mlb_id,
            raw_player=player_label,
            team=asset.from_team or proposal.originating_team,
            acquiring_team=asset.to_team,
            transaction_type=txn_type,
            raw_transaction_type=txn_type.transaction_type,
            cash_considerations=asset.amount,
            notes=asset.notes or proposal.notes,
            proposal=proposal,
        )
        asset.executed_transaction = ledger
        asset.save(update_fields=["executed_transaction", "last_modified"])

    _open_stint(proposal, when)
    proposal.status = models.TransactionProposal.EXECUTED
    proposal.executed_at = timezone.now()
    proposal.save(update_fields=["status", "executed_at", "last_modified"])
    return proposal


def _open_stint(proposal, when):
    player = None
    asset = proposal.assets.filter(player__isnull=False).first()
    if asset:
        player = asset.player
    if proposal.kind in ("il_7", "il_56", "il_eos", "il_covid") and player:
        if models.InjuredListStint.objects.filter(proposal=proposal).exists():
            return
        length = {"il_7": "7", "il_56": "56", "il_eos": "eos", "il_covid": "covid"}[proposal.kind]
        models.InjuredListStint.objects.create(
            proposal=proposal,
            player=player,
            team=proposal.originating_team,
            length=length,
            placed_on=when,
            notes=proposal.notes,
        )
    if proposal.kind == "il_activate":
        models.InjuredListStint.objects.filter(
            player=player, team=proposal.originating_team, active_stint=True
        ).update(active_stint=False)
    if proposal.kind == "restricted_place" and player:
        if not models.RestrictedListStint.objects.filter(proposal=proposal).exists():
            rules = rl_rules((proposal.contract_terms or {}).get("rl_type"))
            models.RestrictedListStint.objects.create(
                proposal=proposal,
                player=player,
                team=proposal.originating_team,
                rl_type=(proposal.contract_terms or {}).get("rl_type") or "",
                counts_against_40=rules.get("counts_against_40", False),
                accrues_service=rules.get("accrues_service", False),
                accrues_salary=rules.get("accrues_salary", False),
                placed_on=when,
                notes=proposal.notes,
            )
    if proposal.kind == "restricted_activate" and player:
        models.RestrictedListStint.objects.filter(
            player=player, team=proposal.originating_team, active_stint=True
        ).update(active_stint=False)


def claim_waiver(user, waiver, notes="", team=None):
    if team is not None:
        team = _resolve_team(team)
    else:
        team = teams_for_user(user).exclude(pk=waiver.placing_team_id).first()
    if team is None:
        raise TransactionError("Claiming a player requires a team.")
    _require_team(user, team)
    if waiver.status != models.Waiver.OPEN:
        raise TransactionError("This waiver is no longer open.")
    if waiver.placing_team_id == team.id:
        raise TransactionError("The club that placed the waiver cannot claim it.")
    claim, created = models.WaiverClaim.objects.get_or_create(
        waiver=waiver,
        team=team,
        defaults={"notes": notes or ""},
    )
    if not created and notes:
        claim.notes = notes
        claim.save(update_fields=["notes", "last_modified"])
    return claim


def submit_draft_pick(user, session, player):
    if session.status != models.DraftSession.OPEN_STATUS:
        raise TransactionError("This draft is not open.")
    pick = session.current_pick
    if pick is None:
        raise TransactionError("No pick is on the clock.")
    if pick.team_id and not teams_for_user(user).filter(pk=pick.team_id).exists():
        raise TransactionError("The club on the clock submits this pick.")
    player = _resolve_player(player)
    if player is None:
        raise TransactionError("Name the player being selected.")
    code = "rule5_draft" if session.draft_type == models.DraftSession.RULE5 else "rule4_draft"
    amount = session.selection_fee or None
    terms = None
    if code == "rule4_draft":
        terms = {"slot_year": session.year}
    proposal = create_proposal(
        user=user,
        team=pick.team,
        code=code,
        source=models.TransactionProposal.API,
        notes=pick.slug or "",
        assets=[
            {
                "asset_type": ASSET_PLAYER,
                "player": player,
                "from_team": pick.original_team or pick.team,
                "to_team": pick.team,
                "draft_pick": pick,
                "amount": amount,
                "contract_terms": terms,
                "raw_label": player.name,
            }
        ],
    )
    # Record the selection on the pick. DraftPick.save() also moves the player
    # onto the club, so this update leaves roster changes for the directors.
    models.DraftPick.objects.filter(pk=pick.pk).update(player=player, player_name=player.name)
    _advance_draft(session, pick)
    return proposal


def _advance_draft(session, pick):
    following = models.DraftPick.objects.filter(
        year=session.year, season=session.half, player__isnull=True
    ).exclude(pk=pick.pk)
    if session.draft_type in ("aa", "open", "balance"):
        following = following.filter(draft_type=session.draft_type)
    following = following.order_by("draft_round", "pick_number", "id")
    nxt = None
    for candidate in following:
        if (candidate.draft_round or 0, candidate.pick_number or 0, candidate.id) > (
            pick.draft_round or 0,
            pick.pick_number or 0,
            pick.id,
        ):
            nxt = candidate
            break
    session.current_pick = nxt
    if nxt is None:
        session.status = models.DraftSession.COMPLETE
    session.save(update_fields=["current_pick", "status", "last_modified"])


def proposal_to_dict(proposal):
    waiver = getattr(proposal, "waiver", None)
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "kind_label": proposal.kind_label,
        "status": proposal.status,
        "source": proposal.source,
        "team_id": proposal.originating_team_id,
        "team": proposal.originating_team.short_name,
        "effective_date": _iso(proposal.effective_date),
        "processing_week": _iso(proposal.processing_week),
        "notes": proposal.notes,
        "contract_terms": proposal.contract_terms,
        "flagged": proposal.flagged,
        "flag_note": proposal.flag_note if proposal.flagged else "",
        "parties": [
            {
                "team_id": party.team_id,
                "team": party.team.short_name,
                "role": party.role,
                "agreement_status": party.agreement_status,
            }
            for party in proposal.parties.select_related("team")
        ],
        "assets": [
            {
                "id": asset.id,
                "asset_type": asset.asset_type,
                "player_id": asset.player_id,
                "player": asset.player.name if asset.player else asset.raw_label,
                "mlb_id": asset.mlb_id,
                "from_team_id": asset.from_team_id,
                "to_team_id": asset.to_team_id,
                "amount": asset.amount,
                "draft_pick_id": asset.draft_pick_id,
                "contract_terms": asset.contract_terms,
                "notes": asset.notes,
                "transaction_id": asset.executed_transaction_id,
            }
            for asset in proposal.assets.select_related("player")
        ],
        "waiver_id": waiver.id if waiver else None,
    }


def _iso(value):
    if value is None:
        return None
    return value.isoformat()


def list_kinds():
    return list(KINDS.values())


def visible_proposals(user):
    teams = teams_for_user(user)
    return (
        models.TransactionProposal.objects.filter(parties__team__in=teams)
        .distinct()
        .select_related("originating_team")
        .prefetch_related("parties__team", "assets")
    )


def submit_from_form(user, form_type, cleaned, source="web"):
    """Turn a web-form payload into a proposal. The form type is the step-1 key."""
    team = _resolve_team(cleaned.get("team"))
    notes = _first(
        cleaned,
        "notes",
        "purpose",
        "reason",
        "details",
        "injury_description",
        "transaction_details",
        "claim_details",
        "contract_details",
    )
    effective = cleaned.get("effective_date") or cleaned.get("retroactive_date")
    player = cleaned.get("player")
    if isinstance(player, str):
        player = None

    if form_type == "trade":
        assets = []
        if isinstance(cleaned.get("player"), models.Player):
            assets.append(
                {
                    "asset_type": ASSET_PLAYER,
                    "player": cleaned["player"],
                    "from_team": team,
                    "to_team": cleaned.get("counterparty"),
                }
            )
        if cleaned.get("pick_label"):
            assets.append(
                {
                    "asset_type": ASSET_DRAFT_PICK,
                    "raw_label": cleaned["pick_label"],
                    "from_team": team,
                    "to_team": cleaned.get("counterparty"),
                }
            )
        if cleaned.get("cash_amount"):
            assets.append(
                {
                    "asset_type": ASSET_CASH,
                    "amount": int(cleaned["cash_amount"]),
                    "raw_label": "Cash Reserves",
                    "from_team": team,
                    "to_team": cleaned.get("counterparty"),
                }
            )
        if cleaned.get("ifa_amount"):
            assets.append(
                {
                    "asset_type": ASSET_IFA,
                    "amount": int(cleaned["ifa_amount"]),
                    "raw_label": "IFA Cap Space",
                    "from_team": team,
                    "to_team": cleaned.get("counterparty"),
                }
            )
        return create_proposal(
            user=user,
            team=team,
            code="trade",
            assets=assets,
            counterparty_team=cleaned.get("counterparty"),
            notes=cleaned.get("notes") or "",
            source=source,
            effective_date=effective,
        )

    if form_type in ("signing", "ifa_signing"):
        code = cleaned.get("signing_kind") or ("ifa_signing" if form_type == "ifa_signing" else "mlb_signing")
        terms = {
            "years": cleaned.get("years") or None,
            "total": cleaned.get("total_amount") or None,
            "points": _decimal(cleaned.get("points")),
            "level": cleaned.get("contract_level") or None,
            "text": cleaned.get("transaction_details") or cleaned.get("notes") or "",
        }
        raw_label = cleaned.get("player_name") or None
        if isinstance(cleaned.get("player"), models.Player):
            player = cleaned["player"]
            raw_label = player.name
        else:
            player = None
        amount = cleaned.get("total_amount") or cleaned.get("amount")
        return create_proposal(
            user=user,
            team=team,
            code=code,
            assets=[
                {
                    "asset_type": ASSET_PLAYER,
                    "player": player,
                    "raw_label": raw_label,
                    "from_team": team,
                    "amount": int(amount) if amount else None,
                    "contract_terms": terms,
                }
            ],
            notes=notes or "",
            source=source,
            effective_date=effective,
            contract_terms=terms,
        )

    if form_type == "waiver_claim" and isinstance(cleaned.get("player"), models.Player):
        open_waiver = models.Waiver.objects.filter(
            player=cleaned["player"], status=models.Waiver.OPEN
        ).first()
        if open_waiver:
            claim_waiver(user, open_waiver, team=team, notes=notes or "")
            return open_waiver.proposal

    code = _code_from_form(form_type, cleaned)
    assets = []
    if isinstance(cleaned.get("player"), models.Player):
        assets.append(
            {
                "asset_type": ASSET_PLAYER,
                "player": cleaned["player"],
                "from_team": team,
                "notes": notes or "",
            }
        )
    terms = None
    if cleaned.get("contract_details") or cleaned.get("transaction_details"):
        terms = {"text": cleaned.get("contract_details") or cleaned.get("transaction_details")}
    return create_proposal(
        user=user,
        team=team,
        code=code,
        assets=assets,
        notes=notes or "",
        source=source,
        effective_date=effective,
        contract_terms=terms,
        waiver_type=cleaned.get("waiver_type") if form_type == "waiver_request" else None,
        veteran_disposition=cleaned.get("veteran_disposition") or "",
        service_class=cleaned.get("service_class") or "",
        rl_type=cleaned.get("reason") if form_type == "restricted_list" else "",
        limbo_reason=cleaned.get("assignment_reason") or "",
    )


def _code_from_form(form_type, cleaned):
    if form_type == "injured_list":
        return IL_FORM_TO_CODE.get(cleaned.get("il_type"), "il_7")
    if form_type == "waiver_request":
        mapped = WAIVER_FORM_TO_CODE.get(cleaned.get("waiver_type"), "waiver_request_outright")
        if mapped == "release":
            return "release"
        return mapped
    if form_type == "offseason":
        return OFFSEASON_FORM_TO_CODE.get(cleaned.get("transaction_type"), "mlb_signing")
    if form_type == "foreign_retirement":
        return FOREIGN_FORM_TO_CODE.get(cleaned.get("transaction_reason"), "retirement")
    if form_type not in FORM_TYPE_TO_CODE:
        raise TransactionError("That transaction type is not available yet.")
    return FORM_TYPE_TO_CODE[form_type]


def _first(cleaned, *keys):
    for key in keys:
        value = cleaned.get(key)
        if value:
            return value
    return ""


def _decimal(value):
    if value in (None, ""):
        return None
    return str(Decimal(value))
