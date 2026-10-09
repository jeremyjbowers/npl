from django.core.management.base import BaseCommand

from npl.sheet_load import load_roster_workbook


class Command(BaseCommand):
    help = "Import contracts and carried salary from the roster tabs."

    def handle(self, *args, **options):
        load_roster_workbook(writer=self.stdout.write)
