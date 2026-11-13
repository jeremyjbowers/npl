"""Delete simulated games, player lines, and standings. MLB lines stay."""

from django.core.management.base import BaseCommand, CommandError

from npl import models
from npl.sim_season import purge_sim


class Command(BaseCommand):
    help = (
        "Clear simulated box scores, the npl player seasons, and the sim standings. "
        "MLB player seasons and franchise team seasons are left in place."
    )

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--week", type=int, default=None, help="Clear one week, then rebuild the season from the games that remain.")

    def handle(self, *args, **options):
        season = models.Season.objects.filter(year=options["season"]).order_by("-is_current", "-id").first()
        if season is None:
            raise CommandError(f"There is no {options['season']} season.")
        if options["week"] is not None and not models.ScheduleWeek.objects.filter(season=season, number=options["week"]).exists():
            raise CommandError(f"{season.year} has no week {options['week']}.")
        result = purge_sim(season, options["week"])
        if options["week"] is None:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cleared {result['games']} games, {result['players']} npl player lines, "
                    f"and {result['teams']} sim team seasons for {season.year}."
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {result['games']} games in week {options['week']}. "
                f"The season now has {result['players']} player lines and {result['teams']} team records."
            )
        )
