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
        stamp = utils.get_timestamp()
        one_week_ago_stamp = stamp - 600000

        for p in models.Player.objects.filter(last_verified__lte=one_week_ago_stamp):
            url = p.mlb_api_url + "?hydrate=currentTeam,team"
            r = requests.get(url)
            player_json = r.json().get('people', None)

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
                    except:
                        pass
                    
                    try:
                        p.weight = player_json['weight']
                    except:
                        pass

                    try:
                        p.bats = player_json['batSide']['code']
                    except:
                        pass

                    try:
                        p.throws = player_json['pitchHand']['code']
                    except:
                        pass
                    
                    try:
                        p.position = player_json['primaryPosition']['abbreviation']
                    except:
                        pass

                    team_abbrev = None

                    if player_json.get('currentTeam', None):
                        if player_json['currentTeam'].get('sport', None):
                            if player_json['currentTeam']['sport']['id'] == 1:
                                # MLB team, get the ID directly
                                team_abbrev = player_json['currentTeam']['abbreviation']
                            else:
                                # MiLB team
                                if player_json['currentTeam'].get('parentOrgId', None):
                                    team_abbrev = requests.get(f'https://statsapi.mlb.com/api/v1/teams/{player_json["currentTeam"]["parentOrgId"]}/').json()['teams'][0]['abbreviation']
                    
                    p.mlb_org = team_abbrev
                    p.last_verified = stamp
                    p.save()
                    print(p)

            time.sleep(1)

            