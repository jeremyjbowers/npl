"""Fold this week's usage into each rostered player's true-talent card."""

from django.core.management.base import BaseCommand, CommandError

from npl import models
from npl.cards import WEEKS
from npl.week_cards import refresh_cards


class Command(BaseCommand):
    help = (
        "Write one weekly card per rostered player. Last year's luck-neutral line "
        "is the prior. The current season's line, diffed against last week's card, is the new usage."
    )

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--week", type=int, required=True)
        parser.add_argument("--team", default=None, help="Abbreviation. Omit it to card every rostered player.")

    def handle(self, *args, **options):
        year = options["season"]
        week = options["week"]
        if week < 1 or week > WEEKS:
            raise CommandError(f"Week must be 1..{WEEKS}.")
        season = models.Season.objects.filter(year=year).order_by("-is_current", "-id").first()
        if season is None:
            raise CommandError(f"There is no {year} season.")

        players = models.Player.objects.filter(team__isnull=False).prefetch_related("stat_seasons")
        if options["team"]:
            players = players.filter(team__abbreviation__iexact=options["team"])
        players = list(players)
        if not players:
            raise CommandError("No rostered players matched.")

        written = refresh_cards(season, week, players)
        self.stdout.write(self.style.SUCCESS(f"Wrote {written} cards for {year} week {week}."))
