from django.core.management.base import BaseCommand

from npl.sheet_load import load_roster_workbook


class Command(BaseCommand):
    help = (
        "Create owner accounts from the Team Owners sheet and the general "
        "manager lines on each roster tab. Reloads the roster snapshot so "
        "those accounts attach to the right clubs."
    )

    def handle(self, *args, **options):
        load_roster_workbook(writer=self.stdout.write)
