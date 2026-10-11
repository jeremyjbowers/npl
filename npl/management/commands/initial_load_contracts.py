from django.core.management.base import BaseCommand
from django.conf import settings

from npl import models, utils
from npl.books import apply_contracts, apply_finances, apply_service_rows
from npl.sheetload import parse_service_sheet, parse_team_sheet


class Command(BaseCommand):
    help = "Load salaries, option colors, buyouts, and the FINANCIALS ledger from each team tab."

    def handle(self, *args, **options):
        models.Contract.objects.all().delete()
        models.ClubLedgerEntry.objects.all().delete()
        models.Player.objects.update(offseason_fa=False)

        for team in models.Team.objects.exclude(tab_id="").exclude(tab_id__isnull=True):
            grid = utils.get_sheet_grid(settings.ROSTER_SHEET_ID, f"{team.tab_id}!A:V")
            if not grid:
                self.stdout.write(f"No sheet for {team}")
                continue
            parsed = parse_team_sheet(grid)
            apply_contracts(team, parsed)
            apply_finances(team, parsed, year=settings.LEAGUE_YEAR)
            self.stdout.write(
                f"{team.short_name}: {len(parsed['players'])} contracts, {len(parsed['lines'])} ledger lines"
            )

        service = utils.get_sheet(settings.ROSTER_SHEET_ID, "Service Time!A:R", value_cutoff=None)
        if service:
            apply_service_rows(parse_service_sheet(service))
            self.stdout.write(f"Service time rows: {len(service) - 1}")
