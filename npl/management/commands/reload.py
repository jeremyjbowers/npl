from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command("migrate")
        call_command('initial_load_npl_roster_sheet')
        call_command('initial_load_contracts')
        call_command('initial_load_transactions')
        # call_command('initial_load_mlb_rosters')
        # call_command('scrape_mlb_info')