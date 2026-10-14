"""Homepage weekly transaction log and the deadlines the app already stores."""

import datetime
from datetime import timedelta

import pytz
from django.db.models import F
from django.utils import timezone

from npl import models
from npl.transactions.trades import trade_card_prefetches

EASTERN = pytz.timezone("US/Eastern")
HOMEPAGE_WEEK_LIMIT = 6
UNOWNED_PLAYER_LIMIT = 40

SEASON_DEADLINES = (
    ("opening_day", "Opening day"),
    ("end_of_season", "End of season"),
    ("ifa_deadline", "IFA deadline"),
    ("term_pay_1", "First term payment"),
    ("term_pay_2", "Second term payment"),
    ("year_end", "Year end"),
)


def week_monday(value):
    """Monday of the Monday–Sunday week that contains this date."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    return value - timedelta(days=value.weekday())


def recent_window_start(today, limit=HOMEPAGE_WEEK_LIMIT):
    """First Monday of the window that includes the previous completed week.

    The current week is inside the span so a Monday processing day is visible.
    The span is one week longer than ``limit`` so an empty current week still
    leaves ``limit`` completed weeks, beginning with the previous one.
    """
    if isinstance(today, datetime.datetime):
        today = today.date()
    return week_monday(today) - timedelta(weeks=limit)


def group_transactions_by_week(rows):
    """Group dated rows by the Monday of their week.

    Dates in the same Monday–Sunday week share one group. The group key is
    that Monday. Groups come back newest Monday first. Rows with no date are
    dropped. Order inside a week is the order the rows were given.
    """
    grouped = {}
    for row in rows:
        monday = week_monday(getattr(row, "date", None))
        if monday is None:
            continue
        grouped.setdefault(monday, []).append(row)
    return [(monday, grouped[monday]) for monday in sorted(grouped, reverse=True)]


def select_homepage_weeks(groups, today, limit=HOMEPAGE_WEEK_LIMIT):
    """Keep up to ``limit`` week groups, newest Monday first.

    Prefer the recent window, which includes the previous completed week.
    If that window has no rows, keep the newest older weeks instead.
    """
    if not groups:
        return []
    start = recent_window_start(today, limit=limit)
    recent = [group for group in groups if group[0] >= start]
    chosen = recent if recent else list(groups)
    chosen.sort(key=lambda group: group[0], reverse=True)
    return chosen[:limit]


def _transaction_queryset():
    return (
        models.Transaction.objects.select_related(
            "player", "team", "acquiring_team", "transaction_type", "trade"
        )
        .defer(
            "player__stats",
            "player__scoresheet_defense",
            "player__scoresheet_offense",
        )
        .prefetch_related(*trade_card_prefetches())
        .order_by("-date", "-id")
    )


def _latest_dated_transactions(limit):
    """Rows from the newest ``limit`` weeks that actually have a date."""
    mondays = []
    seen = set()
    for day in (
        models.Transaction.objects.exclude(date__isnull=True)
        .order_by("-date")
        .values_list("date", flat=True)
        .iterator(chunk_size=1000)
    ):
        monday = week_monday(day)
        if monday in seen:
            continue
        seen.add(monday)
        mondays.append(monday)
        if len(mondays) >= limit:
            break
    if not mondays:
        return []
    oldest = mondays[-1]
    newest_end = mondays[0] + timedelta(days=7)
    return list(_transaction_queryset().filter(date__gte=oldest, date__lt=newest_end))


def transaction_weeks(today=None):
    """Week groups for the homepage log, newest Monday first."""
    today = today or timezone.localdate()
    start = recent_window_start(today)
    rows = list(_transaction_queryset().filter(date__gte=start))
    selected = select_homepage_weeks(group_transactions_by_week(rows), today)
    if not selected:
        selected = select_homepage_weeks(
            group_transactions_by_week(_latest_dated_transactions(HOMEPAGE_WEEK_LIMIT)),
            today,
        )
    from npl.transactions.trades import group_log

    return [
        {"monday": monday, "transactions": week_rows, "blocks": group_log(week_rows)}
        for monday, week_rows in selected
    ]


def _defer_player(queryset):
    return queryset.defer(
        "player__stats",
        "player__scoresheet_defense",
        "player__scoresheet_offense",
    )


def open_auctions(now=None):
    """Auctions still open: active, not a nomination, closing in the future."""
    if now is None:
        now = datetime.datetime.now(EASTERN)
    return list(
        _defer_player(
            models.Auction.objects.filter(active=True, closes__gte=now)
            .exclude(is_nomination=True)
            .select_related("player")
        ).order_by("closes", "id")
    )


def _calendar_date(value):
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, EASTERN)
        return value.date()
    return value


def _clock(value):
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, EASTERN)
        return (value.hour, value.minute, value.second)
    return (0, 0, 0)


def _deadline(when, label):
    return {"when": when, "date": _calendar_date(when), "label": label}


def collect_deadlines(today=None, now=None, auctions=None):
    """Every deadline the app already stores, sorted by date.

    A row is included only when its date exists. Season dates in the past
    are omitted. Auction closes must still be in the future.
    """
    today = today or timezone.localdate()
    if now is None:
        now = datetime.datetime.now(EASTERN)

    from npl.views import get_next_processing_deadline

    rows = [
        _deadline(get_next_processing_deadline(), "Next transaction processing deadline")
    ]

    season = models.Season.objects.filter(is_current=True).order_by("-year").first()
    if season is not None:
        for field, label in SEASON_DEADLINES:
            day = getattr(season, field)
            if day is not None and day >= today:
                rows.append(_deadline(day, label))

    if auctions is None:
        auctions = open_auctions(now)
    for auction in auctions:
        name = auction.player.name if auction.player_id and auction.player else "Auction"
        rows.append(_deadline(auction.closes, name))

    waivers = _defer_player(
        models.Waiver.objects.filter(status=models.Waiver.OPEN).select_related("player")
    )
    for waiver in waivers:
        when = waiver.closes or waiver.clears_on
        if not when:
            continue
        player_name = waiver.player.name if waiver.player_id and waiver.player else "Player"
        rows.append(_deadline(when, f"{player_name} {waiver.get_waiver_type_display()} waiver"))

    assignments = _defer_player(
        models.InLimboAssignment.objects.filter(active_assignment=True)
        .exclude(deadline__isnull=True)
        .select_related("player")
    )
    for assignment in assignments:
        name = assignment.player.name if assignment.player_id else "Player"
        rows.append(_deadline(assignment.deadline, name))

    for event in models.Event.objects.filter(date__gte=today).only("date", "title"):
        if event.date:
            rows.append(_deadline(event.date, event.title))

    rows.sort(key=lambda row: (row["date"], _clock(row["when"]), row["label"]))
    return rows


def unowned_players(limit=UNOWNED_PLAYER_LIMIT):
    """Players with ``is_owned=False``, last name order, capped for the homepage."""
    rows = list(
        models.Player.objects.filter(is_owned=False)
        .defer("stats", "scoresheet_defense", "scoresheet_offense")
        .order_by(
            F("last_name").asc(nulls_last=True),
            F("first_name").asc(nulls_last=True),
            "mlb_id",
        )[: limit + 1]
    )
    return rows[:limit], len(rows) > limit


def board_context(today=None, now=None):
    """Template context for the four homepage sections."""
    from npl.transactions.impact import roster_roundup

    today = today or timezone.localdate()
    if now is None:
        now = datetime.datetime.now(EASTERN)
    auctions = open_auctions(now)
    players, capped = unowned_players()
    return {
        "transaction_weeks": transaction_weeks(today),
        "deadlines": collect_deadlines(today=today, now=now, auctions=auctions),
        "open_auctions": auctions,
        "unowned_players": players,
        "unowned_players_capped": capped,
        "roster_moves": roster_roundup(),
    }
