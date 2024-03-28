from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils


class Command(BaseCommand):
    headers = {
        "Referer": "https://www.milb.com/",
        "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Microsoft Edge";v="115", "Chromium";v="115"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "macOS",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.203",
    }
    def get_cpx_rosters(self):
        roster_urls = []
        for league_url in [self.FCL_URL, self.AZL_URL, self.DSL_URL]:
            r = requests.get(league_url, headers=self.headers)
            soup = BeautifulSoup(r.content, 'html.parser')
            for a in soup.select('a'):
                if a.get('href', None):
                    if '/roster' in a.attrs['href']:
                        roster_urls.append(a.attrs['href'])

        for url in roster_urls:
            tr = requests.get(url, headers=self.headers)

            if tr.status_code == 200:
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
                        player_dict['roster_status'] = "MINORS"

                        if "Injured 7" in cells[6].text.strip():
                            player_dict['roster_status'] = "IL-7"

                        if "Injured 60" in cells[6].text.strip():
                            player_dict['roster_status'] = "IL-60"

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

    def get_milb_rosters(self):
        r = requests.get(self.MILB_AFFILIATE_URL, headers=self.headers)
        soup = BeautifulSoup(r.content, 'html.parser')
        team_urls = [a.attrs['href'] for a in soup.select('a.p-forge-logo--link') if "www" in a.attrs['href']]
        for url in team_urls:

            if url == "https://www.sugarlandskeeters.com/":
                url = "https://www.milb.com/sugar-land"

            if url == "https://www.saintsbaseball.com/":
                url = "https://www.milb.com/st-paul"

            print(f"{url}/roster")

            tr = requests.get(f"{url}/roster", headers=self.headers)

            if tr.status_code == 200:
                ts = BeautifulSoup(tr.content, 'html.parser')
                org = ts.select('button.tabs__filter-buttons--button')[2].text.split(' Transactions')[0].strip()

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
                        player_dict['roster_status'] = "MINORS"
                        player_dict['mlb_org'] = org

                        if "Injured 7" in cells[6].text.strip():
                            player_dict['roster_status'] = "IL-7"

                        if "Injured 60" in cells[6].text.strip():
                            player_dict['roster_status'] = "IL-60"

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
            tr = requests.get(url.replace('depth-chart', '40-man'), headers=self.headers)

            if tr.status_code == 200:
                ts = BeautifulSoup(tr.content, 'html.parser')

                org = settings.MLB_URL_TO_ORG_NAME.get(url.split('mlb.com/')[1].split('/roster')[0].strip(), None)

                player_rows = ts.select('div.players tbody tr')
                for row in player_rows:
                    cells = row.select('td')
                    player_dict = None

                    player_dict = {}
                    player_dict['name'] = cells[1].select('a')[0].text.strip()
                    player_dict['roster_status'] = "MLB"

                    for span in cells[1].select('span'):
                        if "status" in span.attrs['class'][0]:
                            player_dict['roster_status'] = cells[1].select('span')[1].text.strip().upper()

                    player_dict['mlb_id'] = cells[1].select('a')[0].attrs['href'].split('-')[-1].strip().split('/')[-1].strip()
                    year = cells[5].text.strip().split('/')[2]
                    month = cells[5].text.strip().split('/')[0].zfill(2)
                    day = cells[5].text.strip().split('/')[1].zfill(2)
                    player_dict['birthdate'] = f"{year}-{month}-{day}"
                    player_dict['mlb_org'] = org

                    if player_dict:
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

        self.MLB_DEPTH_URL = "https://www.mlb.com/team/roster/depth-chart"
        self.MILB_AFFILIATE_URL = "https://www.milb.com/about/teams/by-affiliate"
        self.FCL_URL = "https://www.milb.com/florida-complex"
        self.AZL_URL = "https://www.milb.com/arizona-complex"
        self.DSL_URL = "https://www.milb.com/dominican-summer"

        self.fix_bad_player_ids()

        # self.get_cpx_rosters()
        self.get_milb_rosters()
        self.get_mlb_rosters()
