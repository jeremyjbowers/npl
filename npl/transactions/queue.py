"""One gameweek of proposals for the directors' list."""

import datetime
from urllib.parse import urlencode

from django.db.models import Count
from django.urls import reverse

from npl import models
from npl.transactions.catalog import KINDS
from npl.transactions.weeks import deadline_for, review_monday

STATUS_LABELS = dict(models.TransactionProposal.STATUS_CHOICES)


def queue_page(moment, week_value, status_value, kind_value):
    """The proposals for one Monday, plus week, kind, and status pickers."""
    status = status_value if status_value in STATUS_LABELS else None
    kind = kind_value if kind_value in KINDS else None
    current = review_monday(moment)
    selected = _parse_week(week_value) or current
    visible = _window(selected)
    others = _other_weeks(visible)
    schedule = {
        row.lineup_due: row
        for row in models.ScheduleWeek.objects.filter(lineup_due__in=[*visible, *others]).select_related("season")
    }
    week_counts = _counts(visible + others, "processing_week", status, kind)
    status_counts = _counts([selected], "status", None, kind)
    kind_counts = _counts([selected], "kind", status, None)

    proposals = _proposals(selected, status, kind)
    return {
        "rows": [_row(proposal, selected, status, kind) for proposal in proposals],
        "selected_week": selected,
        "status": status or "",
        "kind": kind or "",
        "opens": deadline_for(selected - datetime.timedelta(days=7)),
        "closes": deadline_for(selected),
        "weeks": [_week(monday, schedule, current, selected, week_counts, status, kind) for monday in visible],
        "other_weeks": [_week(monday, schedule, current, selected, week_counts, status, kind) for monday in others],
        "kinds": _choices("kind", kind_counts, kind, selected, status, kind),
        "statuses": _choices("status", status_counts, status, selected, status, kind),
    }


def _proposals(monday, status, kind):
    query = _apply(models.TransactionProposal.objects.filter(processing_week=monday), status, kind)
    return query.select_related("originating_team").prefetch_related(
        "parties__team", "assets__player"
    ).order_by("-flagged", "created", "id")


def _apply(query, status, kind):
    if status:
        query = query.filter(status=status)
    if kind:
        query = query.filter(kind=kind)
    return query


def _counts(weeks, field, status, kind):
    """Counts for one column. The column's own filter is left off so every choice stays listed."""
    query = models.TransactionProposal.objects.filter(processing_week__in=weeks)
    if field != "status" and status:
        query = query.filter(status=status)
    if field != "kind" and kind:
        query = query.filter(kind=kind)
    return dict(query.values(field).annotate(n=Count("id")).values_list(field, "n"))


def _window(selected):
    """Two Mondays ahead, the selected Monday, and two behind."""
    return [selected + datetime.timedelta(days=7 * offset) for offset in (2, 1, 0, -1, -2)]


def _other_weeks(visible):
    stored = (
        models.TransactionProposal.objects.exclude(processing_week=None)
        .values_list("processing_week", flat=True)
        .distinct()
    )
    return sorted((day for day in set(stored) if day not in visible), reverse=True)


def _week(monday, schedule, current, selected, counts, status, kind):
    return {
        "monday": monday,
        "label": _week_label(monday, schedule.get(monday)),
        "current": monday == current,
        "selected": monday == selected,
        "count": counts.get(monday, 0),
        "url": _url(monday, status, kind),
    }


def _choices(field, counts, selected_value, monday, status, kind):
    if field == "status":
        catalog = STATUS_LABELS
    else:
        catalog = {code: kind["label"] for code, kind in KINDS.items()}
    choices = [
        {
            "label": "All",
            "selected": not selected_value,
            "count": sum(counts.values()),
            "url": _url(monday, None if field == "status" else status, None if field == "kind" else kind),
        }
    ]
    for code, label in catalog.items():
        count = counts.get(code, 0)
        if not count:
            continue
        choices.append(
            {
                "label": label,
                "selected": code == selected_value,
                "count": count,
                "url": _url(
                    monday,
                    code if field == "status" else status,
                    code if field == "kind" else kind,
                ),
            }
        )
    return choices


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


def _url(monday, status, kind):
    params = {"week": monday.isoformat()}
    if status:
        params["status"] = status
    if kind:
        params["kind"] = kind
    return f"{reverse('proposals')}?{urlencode(params)}"


def _row(proposal, monday, status, kind):
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
        "kind_url": _url(monday, status, proposal.kind),
        "status": proposal.get_status_display(),
        "status_url": _url(monday, proposal.status, kind),
        "filed": proposal.created,
        "pieces": ", ".join(pieces),
        "parties": ", ".join(parties),
        "flagged": proposal.flagged,
        "flag_note": proposal.flag_note,
    }
