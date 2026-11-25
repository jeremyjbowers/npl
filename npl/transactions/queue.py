"""One gameweek of proposals for the directors' list."""

import datetime
from urllib.parse import urlencode

from django.db.models import Count
from django.urls import reverse

from npl import models
from npl.transactions.weeks import deadline_for, processing_monday, review_monday

OPEN = (
    models.TransactionProposal.DRAFT,
    models.TransactionProposal.PROPOSED,
    models.TransactionProposal.AWAITING,
    models.TransactionProposal.AGREED,
)
CLOSED = (
    models.TransactionProposal.REJECTED,
    models.TransactionProposal.WITHDRAWN,
    models.TransactionProposal.EXECUTED,
    models.TransactionProposal.VOIDED,
)
STATES = ("open", "closed", "all")


def queue_page(moment, week_value, state_value):
    """The proposals for one Monday, plus the week and status pickers."""
    state = state_value if state_value in STATES else "open"
    selected = _parse_week(week_value) or review_monday(moment)
    weeks = _week_choices(selected, moment)
    schedule = {
        row.lineup_due: row
        for row in models.ScheduleWeek.objects.filter(lineup_due__in=weeks).select_related("season")
    }
    state_counts = _state_counts(selected)
    week_counts = _week_counts(weeks, state)

    proposals = _proposals(selected, state)
    rows = [_row(proposal) for proposal in proposals]
    return {
        "rows": rows,
        "selected_week": selected,
        "state": state,
        "opens": deadline_for(selected - datetime.timedelta(days=7)),
        "closes": deadline_for(selected),
        "weeks": [
            {
                "monday": monday,
                "label": _week_label(monday, schedule.get(monday)),
                "current": monday == review_monday(moment),
                "selected": monday == selected,
                "count": week_counts.get(monday, 0),
                "url": _url(monday, state),
            }
            for monday in weeks
        ],
        "states": [
            {
                "key": key,
                "label": {"open": "Open", "closed": "Closed", "all": "All"}[key],
                "selected": key == state,
                "count": state_counts[key],
                "url": _url(selected, key),
            }
            for key in STATES
        ],
        "closed_on_this_week": state_counts["closed"],
        "closed_url": _url(selected, "closed"),
    }


def _proposals(monday, state):
    query = models.TransactionProposal.objects.filter(processing_week=monday)
    query = _apply_state(query, state)
    return query.select_related("originating_team").prefetch_related(
        "parties__team", "assets__player"
    ).order_by("-flagged", "created", "id")


def _apply_state(query, state):
    if state == "open":
        return query.filter(status__in=OPEN)
    if state == "closed":
        return query.filter(status__in=CLOSED)
    return query


def _state_counts(monday):
    grouped = dict(
        models.TransactionProposal.objects.filter(processing_week=monday)
        .values("status")
        .annotate(n=Count("id"))
        .values_list("status", "n")
    )
    open_count = sum(grouped.get(status, 0) for status in OPEN)
    closed_count = sum(grouped.get(status, 0) for status in CLOSED)
    return {
        "open": open_count,
        "closed": closed_count,
        "all": open_count + closed_count,
    }


def _week_counts(weeks, state):
    query = models.TransactionProposal.objects.filter(processing_week__in=weeks)
    query = _apply_state(query, state)
    return dict(
        query.values("processing_week").annotate(n=Count("id")).values_list("processing_week", "n")
    )


def _week_choices(selected, moment):
    stored = set(
        models.TransactionProposal.objects.exclude(processing_week=None)
        .values_list("processing_week", flat=True)
        .distinct()
    )
    mondays = set(stored)
    mondays.add(review_monday(moment))
    mondays.add(processing_monday(moment))
    mondays.add(selected)
    mondays.add(selected - datetime.timedelta(days=7))
    mondays.add(selected + datetime.timedelta(days=7))
    return sorted(mondays, reverse=True)


def _parse_week(value):
    if not value:
        return None
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        return None
    if parsed.weekday() != 0:
        parsed -= datetime.timedelta(days=parsed.weekday())
    return parsed


def _week_label(monday, schedule):
    if schedule is not None:
        return f"Week {schedule.number}"
    return "Week of"


def _url(monday, state):
    params = {"week": monday.isoformat()}
    if state != "open":
        params["state"] = state
    return f"{reverse('proposals')}?{urlencode(params)}"


def _row(proposal):
    pieces = []
    for asset in proposal.assets.all():
        if asset.player_id and asset.player:
            pieces.append(asset.player.name)
        elif asset.raw_label:
            pieces.append(asset.raw_label)
        elif asset.amount:
            pieces.append(f"${asset.amount:,}")
        else:
            pieces.append(asset.asset_type.replace("_", " "))
    parties = []
    for party in proposal.parties.all():
        if party.role != models.TransactionParty.COUNTERPARTY or not party.team_id:
            continue
        parties.append(f"{party.team.short_name} ({party.get_agreement_status_display()})")
    club = proposal.originating_team
    return {
        "id": proposal.id,
        "url": reverse("proposal_detail", args=[proposal.id]),
        "club": club.short_name if club else "",
        "club_url": f"/teams/{club.short_name.lower()}/" if club and club.short_name else "",
        "kind": proposal.kind_label,
        "status": proposal.get_status_display(),
        "filed": proposal.created,
        "pieces": ", ".join(pieces),
        "parties": ", ".join(parties),
        "flagged": proposal.flagged,
        "flag_note": proposal.flag_note,
    }
