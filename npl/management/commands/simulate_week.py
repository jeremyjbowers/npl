"""Simulate one week of games. Meant for cron, not the website."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from npl import models
from npl.engine_client import EngineUnavailable
from npl.sim_cards import SimError
from npl.sim_week import simulate_week


class Command(BaseCommand):
    help = (
        "Play one week from the filed cards. Box scores land on the games, "
        "player lines are stored as npl seasons, and standings land on the sim team seasons."
    )

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--week", type=int, default=None, help="Week number. Omit it to play the week simulated today.")

    def handle(self, *args, **options):
        season = models.Season.objects.filter(year=options["season"]).order_by("-is_current", "-id").first()
        if season is None:
            raise CommandError(f"There is no {options['season']} season.")
        week = _week(season, options["week"])
        try:
            result = simulate_week(season, week, _engine())
        except EngineUnavailable as error:
            raise CommandError(str(error)) from error
        except SimError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Week {week.number}: played {result['played']}, skipped {result['skipped']}. "
                f"Wrote {result['players']} player lines and {result['teams']} team records."
            )
        )


def _week(season, number):
    if number is None:
        today = timezone.localdate()
        week = models.ScheduleWeek.objects.filter(season=season, simulated_on=today).first()
        if week is None:
            raise CommandError(f"No week is simulated on {today.isoformat()}. Pass --week.")
        return week
    week = models.ScheduleWeek.objects.filter(season=season, number=number).first()
    if week is None:
        raise CommandError(f"{season.year} has no week {number}.")
    return week


def _engine():
    from npl import engine_client

    return engine_client
