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
        print("NO NAMES")
        for p in models.Player.objects.filter(name__isnull=True):
            r = requests.get(p.mlb_api_url + "?hydrate=currentTeam,team")
            
            player_json = r.json().get('people', None)

            print(p.mlb_api_url + "?hydrate=currentTeam,team")

            if player_json:
                if len(player_json) == 1:
                    player_json = player_json[0]
                    p.active = player_json['active']
                    p.birthdate = player_json['birthDate']
                    p.name = player_json['fullName']
                    p.last_name = player_json['lastName']
                    p.first_name = player_json['firstName']

                    try:
                        p.height = player_json['height']
                        p.weight = player_json['weight']
                        p.bats = player_json['batSide']['code']
                        p.throws = player_json['pitchHand']['code']

                    except KeyError:
                        pass
                    p.save()
                    print(p)

        print("NO BIRTHDATE")
        for p in models.Player.objects.filter(birthdate__isnull=True):
            r = requests.get(p.mlb_api_url + "?hydrate=currentTeam,team")
            
            player_json = r.json().get('people', None)

            print(p.mlb_api_url + "?hydrate=currentTeam,team")

            if player_json:
                if len(player_json) == 1:
                    player_json = player_json[0]
                    p.active = player_json['active']
                    p.birthdate = player_json['birthDate']

                    try:
                        p.height = player_json['height']
                        p.weight = player_json['weight']
                        p.bats = player_json['batSide']['code']
                        p.throws = player_json['pitchHand']['code']

                    except KeyError:
                        pass
                    p.save()
                    print(p)

            time.sleep(random.choice([1,2]))

        print("NO MLB_ORG")
        for p in models.Player.objects.filter(mlb_org__isnull=True):
            r = requests.get(p.mlb_api_url + "?hydrate=currentTeam,team")

            player_json = r.json().get('people', None)
            print(p.mlb_api_url + "?hydrate=currentTeam,team")


            if player_json:
                if len(player_json) == 1:
                    player_json = player_json[0]
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

            