import time
import random

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        for p in models.Player.objects.filter(mlb_org__isnull=True):
            """
            http://statsapi.mlb.com/api/v1/teams/111/roster/fullRoster?season=2023
            """
            r = requests.get(p.mlb_api_url + "?hydrate=currentTeam,team")
            player_json = r.json()['people'][0]

            if player_json.get('currentTeam', None):
                org_id = None

                if player_json['currentTeam'].get('parentOrgId', None):
                    org_id = player_json['currentTeam']['parentOrgId']
                else:
                    org_id = player_json['currentTeam']['id']

                try:
                    rorg = requests.get(f'https://statsapi.mlb.com/api/v1/teams/{org_id}')
                    org_json = rorg.json()['teams'][0]
                    p.mlb_org = org_json['abbreviation']
                    p.save()
                    print(p)
                
                except:
                    pass

                time.sleep(random.choice([1,2]))

            # p.birthdate = player_json['birthDate']
            # p.height = player_json['height']
            # p.weight = player_json['weight']
            # p.bats = player_json['batSide']['code']
            # p.throws = player_json['pitchHand']['code']
            # p.save()
            # time.sleep(random.choice([1,2,3]))
            # time.sleep(1)

            # transaction_rows = soup.select('section#transactions tr')
            # for row in transaction_rows:
            #     print(row.select('td'))
            #     cells = row.select('td')
            #     raw_date = cells[1].text
            #     parsed_date = parse(raw_date).date
            #     note = cells[2].text

            #     try:
            #         obj = models.Transaction.objects.get(player=p, date=parsed_date, is_mlb_transaction=True, note=note)
            #     except models.Transaction.DoesNotExist:
            #         obj = models.Transaction(player=p, date=parsed_date, is_mlb_transaction=True, notes=note)
            #         obj.save()




