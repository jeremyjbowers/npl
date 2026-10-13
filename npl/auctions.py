"""In-season free-agent nominations.

During the regular season an unowned player who has appeared in the majors
goes straight onto that week's auction. Every nomination closes Friday at
3 PM Eastern. Each club bids its highest price once. The winner pays one
dollar more than the second-highest bid.

The IFA nomination is only for a player who meets the international
free-agent rules in ``npl.ifa``. Offseason point auctions are a different
process and are not created here.
"""

import datetime

import pytz
from django.db import transaction
from django.utils import timezone

from npl import ifa, models

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


OUT_OF_SEASON = (
    "In-season free-agent auctions run during the regular season. "
    "Offseason auctions are a separate process."
)


def previously_owned_ids(mlb_ids):
    """Players with an NPL ledger row or contract, whether or not they are owned now."""
    ids = [str(mlb_id) for mlb_id in mlb_ids if mlb_id]
    if not ids:
        return set()
    found = set(models.Transaction.objects.filter(player_id__in=ids).values_list("player_id", flat=True))
    found.update(models.Transaction.objects.filter(mlb_id__in=ids).values_list("mlb_id", flat=True))
    found.update(models.Contract.objects.filter(player_id__in=ids).values_list("player_id", flat=True))
    return {str(mlb_id) for mlb_id in found if mlb_id}


def player_was_owned(player):
    if getattr(player, "has_been_rostered", False):
        return True
    return str(getattr(player, "mlb_id", "") or "") in previously_owned_ids([getattr(player, "mlb_id", None)])


def nomination_state(player, phase=None, season=None, today=None, previously_owned=None):
    """Whether the free-agent and IFA buttons should be clickable, and why not.

    ``show_ifa`` is the eligibility rule. The button is hidden when it is false.
    ``can_ifa`` also requires the regular-season auction window.
    """
    if today is None:
        today = datetime.datetime.now(EASTERN).date()
    if season is None:
        season = models.Season.current()
    if phase is None:
        phase = season.phase if season is not None else models.Season.OFFSEASON
    owned = bool(player.is_owned or player.team_id)
    debut = player.has_appeared_in_majors
    can_fa = False
    can_ifa = False
    show_ifa = False
    if owned:
        fa_reason = f"{player.name} is already owned."
        ifa_reason = fa_reason
    else:
        if previously_owned is None:
            previously_owned = player_was_owned(player)
        else:
            previously_owned = bool(previously_owned) or bool(getattr(player, "has_been_rostered", False))
        eligible, ifa_reason = ifa.eligibility(
            player,
            season=season,
            today=today,
            previously_owned=previously_owned,
        )
        show_ifa = eligible
        if phase != models.Season.REGULAR:
            fa_reason = OUT_OF_SEASON
            if eligible:
                ifa_reason = OUT_OF_SEASON
        elif debut is None:
            fa_reason = "Majors debut has not been checked yet, so this player cannot be nominated."
        elif debut is False:
            if eligible:
                fa_reason = "This player has not appeared in the majors. Use the IFA nomination."
            else:
                fa_reason = ifa_reason
        else:
            fa_reason = ""
            can_fa = True
        if eligible and phase == models.Season.REGULAR:
            ifa_reason = ""
            can_ifa = True
    return {
        "can_fa": can_fa,
        "can_ifa": can_ifa,
        "show_ifa": show_ifa,
        "fa_reason": fa_reason,
        "ifa_reason": ifa_reason,
    }


def attach_nomination_flags(players, phase=None, season=None, today=None):
    players = list(players)
    if today is None:
        today = datetime.datetime.now(EASTERN).date()
    if season is None:
        season = models.Season.current()
    if phase is None:
        phase = season.phase if season is not None else models.Season.OFFSEASON
    owned_ids = previously_owned_ids([player.mlb_id for player in players])
    for player in players:
        prior = str(player.mlb_id) in owned_ids or bool(player.has_been_rostered)
        state = nomination_state(
            player,
            phase=phase,
            season=season,
            today=today,
            previously_owned=prior,
        )
        player.can_nominate_fa = state["can_fa"]
        player.can_nominate_ifa = state["can_ifa"]
        player.show_ifa = state["show_ifa"]
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
