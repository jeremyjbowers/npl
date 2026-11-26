from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils
from npl.directors import grant_director_staff


class Command(BaseCommand):
    def handle(self, *args, **options):
        call_command('migrate')
        updated, missing = grant_director_staff()
        if updated:
            self.stdout.write("Director staff: " + ", ".join(updated))
        if missing:
            self.stdout.write(self.style.WARNING("No login account yet for: " + ", ".join(missing)))
        # The bucket copy can be older in content and newer by timestamp.
        # collectstatic then skips it. Clear first so the new CSS is uploaded.
        call_command("collectstatic", "--noinput", "--clear")
        call_command('util_save_all_players')