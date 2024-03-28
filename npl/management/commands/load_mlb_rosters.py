from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils


class Command(BaseCommand):
    mlb_lookup = {
        "108": "LAA",
        "109": "AZ",
        "110": "BAL",
        "111": "BOS",
        "112": "CHC",
        "113": "CIN",
        "114": "CLE",
        "115": "COL",
        "116": "DET",
        "117": "HOU",
        "118": "KC",
        "119": "LAD",
        "120": "WSH",
        "121": "NYM",
        "133": "OAK",
        "134": "PIT",
        "135": "SD",
        "136": "SEA",
        "137": "SF",
        "138": "STL",
        "139": "TB",
        "140": "TEX",
        "141": "TOR",
        "142": "MIN",
        "143": "PHI",
        "144": "ATL",
        "145": "CWS",
        "146": "MIA",
        "147": "NYY",
        "158": "MIL",
    }
    
    def get_rosters(self):
        models.Player.objects.all().update(roster_status="MINORS")
        team_list_url = "https://statsapi.mlb.com/api/v1/teams/"

        r = requests.get(team_list_url)
        team_list = r.json()['teams']

        mlb_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 1]
        aaa_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 11]
        aa_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 12]
        high_a_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 13]
        a_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 14]
        # ss_a_teams =  [self.parse_players(t) for t in team_list if t['sport']['id'] == 15]
        # rookie_teams = [self.parse_players(t) for t in team_list if t['sport']['id'] == 16]            

    def parse_players(self, t):
        roster_link = f"https://statsapi.mlb.com/api/v1/teams/{t['id']}/roster/40Man"
        tr = requests.get(roster_link).json()

        if t['sport']['id'] != 1:
            mlb_team = self.mlb_lookup[str(t['parentOrgId'])]
        
        else:
            mlb_team = t['abbreviation']

        for p in tr['roster']:
            player_dict = {}
            player_dict['mlb_id'] = p['person']['id']
            player_dict['name'] = p['person']['fullName']
            player_dict['position'] = p['position']['abbreviation']
            player_dict['mlb_org'] = mlb_team

            if "injured" in p['status']['description'].lower():
                if "10" in p['status']['description']:
                    player_dict['roster_status'] = "IL-10"
                if "15" in p['status']['description']:
                    player_dict['roster_status'] = "IL-15"
                if "60" in p['status']['description']:
                    player_dict['roster_status'] = "IL-60"

            if t['sport']['id'] == 1:
                if 'active' in p['status']['description'].lower():
                    player_dict['roster_status'] = "MLB"

            try:
                obj = models.Player.objects.get(mlb_id=player_dict['mlb_id'])
            
            except models.Player.DoesNotExist:
                obj = models.Player()
            
            for k,v in player_dict.items():
                setattr(obj, k, v)

            obj.save()
            print(obj)

    def fix_bad_player_ids(self):
        bad_ids = models.Player.objects.filter(mlb_id__icontains="/")
        print(bad_ids.count())

        bad_ids.delete()

        bad_ids = models.Player.objects.filter(mlb_id__icontains="/")
        print(bad_ids.count())

    def handle(self, *args, **options):
        self.fix_bad_player_ids()
        self.get_rosters()
