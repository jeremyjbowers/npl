from django.core.management.base import BaseCommand

from npl.sheet_load import load_roster_workbook


class Command(BaseCommand):
    help = "Import clubs from the roster workbook tabs. Also loads players, money, and owners."

    def handle(self, *args, **options):
        load_roster_workbook(writer=self.stdout.write)
