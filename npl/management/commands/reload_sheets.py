from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Update the universe of players from MLB
        call_command('load_mlb_rosters')

        # Roster tabs are the opening snapshot: clubs, MLB IDs, money, owners.
        call_command('load_roster_workbook')
        call_command('initial_load_transactions')