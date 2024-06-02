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
        call_command('load_mlb_stats')

        # Update NPL specific data
        call_command('initial_load_npl_roster_sheet')
        call_command('initial_load_contracts')
        call_command('initial_load_transactions')