import os

os.environ["DJANGO_COLORS"] = "nocolor"

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    def handle(self, *args, **options):
        os.system("dropdb npl")
        os.system("createdb npl")
        os.system("psql npl < data/sql/npl.sql")