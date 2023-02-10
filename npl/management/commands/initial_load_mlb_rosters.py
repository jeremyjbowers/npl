from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils


class Command(BaseCommand):
    def get_milb_rosters(self):
        r = requests.get(self.MILB_AFFILIATE_URL)
        soup = BeautifulSoup(r.content, 'html.parser')
        team_urls = [a.attrs['href'] for a in soup.select('a.p-forge-logo--link') if "www" in a.attrs['href']]
        for url in team_urls:
            tr = requests.get(f"{url}/roster")
            ts = BeautifulSoup(tr.content, 'html.parser')
            
            player_rows = ts.select('div.players tr')
            for row in player_rows:
                cells = row.select('td')
                player_dict = None
                try:
                    player_dict = {}
                    player_dict['name'] = cells[1].select('a')[0].text.strip()
                    player_dict['mlb_id'] = cells[1].select('a')[0].attrs['href'].split('/')[-1].strip()
                    year = cells[5].text.strip().split('/')[2]
                    month = cells[5].text.strip().split('/')[0].zfill(2)
                    day = cells[5].text.strip().split('/')[1].zfill(2)
                    player_dict['birthdate'] = f"{year}-{month}-{day}"

                except:
                    pass
                    
                if player_dict:
                    try:
                        obj = models.Player.objects.get(mlb_id=player_dict['mlb_id'])
                    
                    except models.Player.DoesNotExist:
                        obj = models.Player()
                    
                    for k,v in player_dict.items():
                        setattr(obj, k, v)

                    obj.save()
                    print(obj)

    def get_mlb_rosters(self):
        r = requests.get(self.MLB_DEPTH_URL)
        soup = BeautifulSoup(r.content, 'html.parser')

        team_urls = [a.attrs['href'] for a in soup.select('a') if "roster" in a.attrs['href'] and "www" in a.attrs['href']]

        for url in team_urls:
            tr = requests.get(url.replace('depth-chart', '40-man'))
            ts = BeautifulSoup(tr.content, 'html.parser')
            
            player_rows = ts.select('div.players tr')
            for row in player_rows:
                cells = row.select('td')
                player_dict = None
                try:
                    player_dict = {}
                    player_dict['name'] = cells[1].select('a')[0].text.strip()
                    player_dict['mlb_id'] = cells[1].select('a')[0].attrs['href'].split('-')[-1].strip()
                    year = cells[5].text.strip().split('/')[2]
                    month = cells[5].text.strip().split('/')[0].zfill(2)
                    day = cells[5].text.strip().split('/')[1].zfill(2)
                    player_dict['birthdate'] = f"{year}-{month}-{day}"

                except:
                    pass
                    
                if player_dict:
                    try:
                        obj = models.Player.objects.get(mlb_id=player_dict['mlb_id'])
                    
                    except models.Player.DoesNotExist:
                        obj = models.Player()
                    
                    for k,v in player_dict.items():
                        setattr(obj, k, v)

                    obj.save()
                    print(obj)

    def handle(self, *args, **options):

        self.MLB_DEPTH_URL = "https://www.mlb.com/team/roster/depth-chart"
        self.MILB_AFFILIATE_URL = "https://www.milb.com/about/teams/by-affiliate"

        self.get_milb_rosters()
        self.get_mlb_rosters()


