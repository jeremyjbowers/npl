from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Count

import ujson as json

from npl import models, utils

class Command(BaseCommand):

    def handle(self, *args, **options):
        models.Player.objects.all().update(roster_status=None, mlb_org=None)
        with open('data/rosters/all_mlb_rosters.json', 'r') as readfile:
            players = json.loads(readfile.read())

            for p in players:
                try:
                    obj = models.Player.objects.get(mlb_id=p['mlb_id'])

                    if not obj.birthdate:
                        if p.get('birthdate', None):
                            obj.birthdate = p['birthdate']

                    if p.get('roster_status', None):
                        obj.roster_status = p['roster_status']

                    if p.get('mlb_org', None):
                        obj.mlb_org = p['mlb_org']

                    obj.save()
                    print(obj)

                except models.Player.DoesNotExist:
                    pass