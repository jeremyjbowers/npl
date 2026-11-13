"""Draw one season of weekly series."""

import secrets
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from npl import models
from npl.schedule import ScheduleError, build_season_plan, default_opening_day, save_season_plan


class Command(BaseCommand):
    help = "Generate a season of 27 weekly series, six games each. Lineups are due Monday. Games are simulated Sunday."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, help="Season year, for example 2026")
        parser.add_argument("--seed", type=int, default=None, help="Seed for a reproducible draw.")
        parser.add_argument("--dry-run", action="store_true", help="Print the draw without saving it.")
        parser.add_argument("--opening-day", default=None, help="YYYY-MM-DD. Otherwise the season's opening day is used.")

    def handle(self, *args, **options):
        year = options["season"]
        season = models.Season.objects.filter(year=year).order_by("-is_current", "-id").first()
        if season is None:
            raise CommandError(f"There is no {year} season.")

        seed = options["seed"]
        if seed is None:
            seed = secrets.randbelow(2**31)

        if options["opening_day"]:
            try:
                opening = datetime.strptime(options["opening_day"], "%Y-%m-%d").date()
            except ValueError as error:
                raise CommandError("--opening-day must be YYYY-MM-DD.") from error
        else:
            opening = season.opening_day or default_opening_day(year)

        teams = models.Team.objects.filter(active=True, league__isnull=False, division__isnull=False).select_related(
            "league", "division"
        )
        try:
            plan = build_season_plan(teams, seed, opening)
        except ScheduleError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(f"Season: {year}")
        self.stdout.write(f"Seed: {seed}")
        self.stdout.write(f"Opening day: {opening.isoformat()}")
        for week in plan:
            pairings = ", ".join(
                f"{series.road.abbreviation} at {series.home.abbreviation}" for series in week.series
            )
            self.stdout.write(
                f"Week {week.number}: {week.kind}, due {week.lineup_due.isoformat()}, "
                f"sim {week.simulated_on.isoformat()}: {pairings}"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing saved."))
            return

        if models.ScheduleWeek.objects.filter(season=season).exists():
            self.stdout.write(self.style.WARNING(f"Replacing the {year} schedule and the weekly plans filed against it."))

        try:
            weeks, series, games = save_season_plan(season, plan, seed)
        except ScheduleError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Saved {weeks} weeks, {series} series, and {games} games for {year}."))
