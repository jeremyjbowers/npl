"""Which Monday a filing is processed on.

Transactions are processed Mondays at 1:00 PM Eastern. A filing before that
cutoff belongs to that Monday. A filing at or after the cutoff belongs to
the next Monday, which is how one that misses by a few hours lands on a
different gameweek.
"""

import datetime

import pytz
from django.utils import timezone

EASTERN = pytz.timezone("US/Eastern")
CUTOFF_HOUR = 13


def processing_monday(moment=None):
    """The Monday a filing made at ``moment`` is processed."""
    moment = _as_eastern(moment)
    monday = moment.date() - datetime.timedelta(days=moment.weekday())
    if moment >= deadline_for(monday):
        monday += datetime.timedelta(days=7)
    return monday


def review_monday(moment=None):
    """The week directors are working.

    After Monday's cutoff, that Monday stays the default through the end of
    the day. A filing from the last few hours is on the following Monday.
    """
    moment = _as_eastern(moment)
    monday = moment.date() - datetime.timedelta(days=moment.weekday())
    if moment.weekday() == 0 and moment >= deadline_for(monday):
        return monday
    return processing_monday(moment)


def deadline_for(monday):
    """1:00 PM Eastern on this Monday."""
    if isinstance(monday, datetime.datetime):
        monday = monday.date()
    naive = datetime.datetime(monday.year, monday.month, monday.day, CUTOFF_HOUR, 0, 0)
    return EASTERN.localize(naive)


def _as_eastern(moment):
    if moment is None:
        moment = timezone.now()
    if isinstance(moment, datetime.datetime):
        if timezone.is_naive(moment):
            moment = EASTERN.localize(moment)
        return moment.astimezone(EASTERN)
    # A bare date is the morning of that day, before the cutoff.
    return EASTERN.localize(datetime.datetime(moment.year, moment.month, moment.day, 9, 0))
