from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Count

import requests
from bs4 import BeautifulSoup

from npl import models, utils


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--trial", action="store_true", help="Explain the duplicates but don't delete anything")

    def fix_fg_dupes(self, *args, **options):
        d1 = (
            models.Player.objects.exclude(fg_id__isnull=True).values('fg_id')
            .annotate(count=Count('mlb_id'))
            .values('fg_id')
            .order_by()
            .filter(count__gt=1)
        )

        print(f"initial FG duplicates: {d1.count()}")

        if not options['trial']:
            for d in d1:
                objs = models.Player.objects.filter(fg_id=d['fg_id'])
                for o in objs:
                    o.fg_id = None
                    o.save()

            d2 = (
                models.Player.objects.exclude(fg_id__isnull=True).values('fg_id')
                .annotate(count=Count('mlb_id'))
                .values('fg_id')
                .order_by()
                .filter(count__gt=1)
            ) 

            print(f"remaining FG duplicates: {d2.count()}")
            for d in d2:
                print(d)

    def handle(self, *args, **options):
        self.fix_fg_dupes(*args, **options)