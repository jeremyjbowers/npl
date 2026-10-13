"""In-season free-agent nominations.

During the regular season an unowned player who has appeared in the majors
goes straight onto that week's auction. Every nomination closes Friday at
3 PM Eastern. Each club bids its highest price once. The winner pays one
dollar more than the second-highest bid.

Players who have not appeared in the majors use the separate IFA nomination.
Offseason point auctions are a different process and are not created here.
"""

import datetime

import pytz
from django.db import transaction
from django.utils import timezone

from npl import models

EASTERN = pytz.timezone("US/Eastern")


class NominationError(Exception):
    pass


def next_friday_3pm(current_time=None):
    """The Friday 3 PM Eastern close for the auction that is open now."""
    if current_time is None:
        current_time = datetime.datetime.now(EASTERN)
    elif timezone.is_naive(current_time):
        current_time = EASTERN.localize(current_time)
    else:
        current_time = current_time.astimezone(EASTERN)
    days_until_friday = (4 - current_time.weekday()) % 7
    if days_until_friday == 0 and current_time.hour >= 15:
        days_until_friday = 7
    friday = current_time + datetime.timedelta(days=days_until_friday)
    return friday.replace(hour=15, minute=0, second=0, microsecond=0)


def nomination_state(player, phase=None):
    """Whether the free-agent and IFA buttons should be clickable, and why not."""
    if phase is None:
        phase = models.Season.league_phase()
    owned = bool(player.is_owned or player.team_id)
    debut = player.has_appeared_in_majors
    can_fa = False
    can_ifa = False
    if owned:
        fa_reason = f"{player.name} is already owned."
        ifa_reason = fa_reason
    else:
        if phase != models.Season.REGULAR:
            fa_reason = (
                "In-season free-agent auctions run during the regular season. "
                "Offseason auctions are a separate process."
            )
        elif debut is None:
            fa_reason = (
                "Majors debut has not been checked yet, so this player cannot be nominated."
            )
        elif debut is False:
            fa_reason = "This player has not appeared in the majors. Use the IFA nomination."
        else:
            fa_reason = ""
            can_fa = True
        if debut is True:
            ifa_reason = "This player has appeared in the majors. Use the free-agent nomination."
        elif debut is None:
            ifa_reason = (
                "Majors debut has not been checked yet, so this player cannot be nominated for an IFA auction."
            )
        else:
            ifa_reason = ""
            can_ifa = True
    return {
        "can_fa": can_fa,
        "can_ifa": can_ifa,
        "fa_reason": fa_reason,
        "ifa_reason": ifa_reason,
    }


def attach_nomination_flags(players, phase=None):
    if phase is None:
        phase = models.Season.league_phase()
    for player in players:
        state = nomination_state(player, phase)
        player.can_nominate_fa = state["can_fa"]
        player.can_nominate_ifa = state["can_ifa"]
        player.fa_nominate_reason = state["fa_reason"]
        player.ifa_nominate_reason = state["ifa_reason"]
    return players


def nominate_player(team, player, kind, reason=""):
    """Put an eligible unowned player on this Friday's auction.

    ``kind`` is ``fa`` or ``ifa``. Returns the auction.
    """
    kind = (kind or "fa").strip().lower()
    if kind not in {"fa", "ifa"}:
        raise NominationError("Choose a free-agent nomination or an IFA nomination.")
    state = nomination_state(player)
    if kind == "fa" and not state["can_fa"]:
        raise NominationError(state["fa_reason"])
    if kind == "ifa" and not state["can_ifa"]:
        raise NominationError(state["ifa_reason"])

    now = datetime.datetime.now(EASTERN)
    closes = next_friday_3pm(now)
    existing = (
        models.Auction.objects.filter(player=player, active=True, closes__gte=now)
        .order_by("closes")
        .first()
    )
    if existing:
        raise NominationError(
            f"{player.name} is already on an auction that closes {existing.closes.strftime('%A, %B %d at %I:%M %p ET')}."
        )

    if kind == "fa":
        auction_kind = models.Auction.IN_SEASON
        label = "free-agent"
    else:
        auction_kind = models.Auction.IFA
        label = "IFA"
    reason = (reason or "").strip()[:500]

    with transaction.atomic():
        auction = models.Auction.objects.create(
            player=player,
            closes=closes,
            is_nomination=False,
            min_bid=1,
            active=True,
            auction_kind=auction_kind,
            bid_unit=models.Auction.DOLLARS,
        )
        models.PlayerNomination.objects.create(
            auction=auction,
            nominating_team=team,
            reason=reason,
        )
    auction.nomination_label = label
    return auction
