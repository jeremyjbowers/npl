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
        for p in models.Player.objects.filter(checked=False):
            print(f"{p.name}\t{p.mlb_api_url}")
            r = requests.get(p.mlb_api_url)
            player_json = r.json()['people'][0]

            p.birthdate = player_json['birthDate']
            p.height = player_json['height']
            p.weight = player_json['weight']
            p.bats = player_json['batSide']['code']
            p.throws = player_json['pitchHand']['code']
            p.checked=True
            p.save()
            time.sleep(random.choice([1,2,3]))

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




