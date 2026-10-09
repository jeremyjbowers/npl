from django.core.management.base import BaseCommand

from npl.sheet_load import load_roster_workbook


class Command(BaseCommand):
    help = "Import roster tabs. Players are matched only by MLB ID."

    def handle(self, *args, **options):
        load_roster_workbook(writer=self.stdout.write)
