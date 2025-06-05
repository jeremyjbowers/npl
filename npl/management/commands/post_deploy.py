from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('migrate')
        call_command("collectstatic", "--noinput")
        call_command('create_cache_table')
        call_command('util_save_all_players')