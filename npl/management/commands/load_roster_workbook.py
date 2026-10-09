from django.core.management.base import BaseCommand

from npl.sheet_load import load_roster_workbook


class Command(BaseCommand):
    help = (
        "Import teams, players (by MLB ID), contracts, carried salary, and "
        "owner accounts from the roster workbook. The sheet is the opening "
        "snapshot. After this load, the site holds those records."
    )

    def add_arguments(self, parser):
        parser.add_argument("--team", dest="team_name", default="", help="Only load tabs whose title contains this text.")

    def handle(self, *args, **options):
        load_roster_workbook(team_name=options["team_name"], writer=self.stdout.write)
