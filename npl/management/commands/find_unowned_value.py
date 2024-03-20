import csv
import os
import time

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models.functions import Greatest
from django.db.models import Max

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import ujson as json
import requests

from npl import models, utils


class Command(BaseCommand):
    draft_sheet = utils.get_sheet("1UQv_vnBBWUT8BiFRd7tAbvW4COWJ61BNkme7iyzf5po", f"2024 Rule 4!A:AA", value_cutoff=None)
    pref_sheet = utils.get_sheet("1woZ7wBsOsqF6itlLNi8In4BL1gy-oWrn7CFJI511dRw", f"2024 R4!A:L", value_cutoff=None)[1:]
    num_players = 20

    def handle(self, *args, **options):
        headers = ["rk","player","mlbid","position","mlb","type","t_rk","fv","R","WR","yes","notes"]    
        taken_mlbids = [slot[14].strip() for slot in self.draft_sheet if slot[0] !="" and slot[14].strip() != ""][:263]
        available_players = [dict(zip(headers,p)) for p in self.pref_sheet if p[2].strip() not in taken_mlbids]

        print(f"Next {self.num_players} players >>")
        for p in available_players[:self.num_players]:
            if p.get('yes', ''):
                print(f"!! {p['mlbid']} {p['rk']}. {p['position']} {p['player']} - {p['WR']}\n  {p.get('notes', '-')}\n")
            else:
                print(f"{p['mlbid']} {p['rk']}. {p['position']} {p['player']} - {p['WR']}\n  {p.get('notes', '-')}\n")

        # players = [dict(zip(headers,p)) for p in utils.get_sheet("1woZ7wBsOsqF6itlLNi8In4BL1gy-oWrn7CFJI511dRw", f"2024 R4!A:L", value_cutoff=None) if p[1].strip() != ""]
        # for p in players:
        #     if p['mlbid'].strip() == "":
        #         BASE_URL = "https://yvo49oxzy7-dsn.algolia.net/1/indexes/*/queries?x-algolia-api-key=2305f7af47eda36d30e1fa05f9986e56&x-algolia-application-id=YVO49OXZY7"

        #         name = p['player']
        #         data = {}

        #         data["requests"] = [
        #             {"indexName":"mlb-players","params":f"query={name}"},
        #         ]

        #         headers = {}
        #         headers['Accept'] = "*/*"
        #         headers['Accept-Encoding'] = "gzip, deflate, br"
        #         headers['Accept-Language'] = "en-US,en;q=0.9"
        #         headers['Connection'] = "keep-alive"
        #         headers['Content-Length'] = "603"
        #         headers['Host'] = "yvo49oxzy7-dsn.algolia.net"
        #         headers['Origin'] = "https://www.mlb.com"
        #         headers['Sec-Fetch-Dest'] = "empty"
        #         headers['Sec-Fetch-Mode'] = "cors"
        #         headers['Sec-Fetch-Site'] = "cross-site"
        #         headers['User-Agent'] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.70"
        #         headers['content-type'] = "application/x-www-form-urlencoded"
        #         headers['sec-ch-ua'] = '"Not_A Brand";v="99", "Microsoft Edge";v="109", "Chromium";v="109"'
        #         headers['sec-ch-ua-mobile'] = "?0"
        #         headers['sec-ch-ua-platform'] = '"macOS"'

        #         r = requests.post(BASE_URL, headers=headers, data=json.dumps(data))

        #         results = r.json()['results']
        #         if len(results[0]['hits']) > 0:
        #             mlb_id = results[0]['hits'][0]['url'].split('player/')[1].replace('/', '')
        #             print(f"{p['player']},{mlb_id}")
        #             time.sleep(0.5)
        #         else:
        #             print(f"{p['player']},")



        # OpenAI.api_key = os.environ.get('OPENAI_API_KEY', None)
        # client = OpenAI()
        # players = utils.get_sheet("1woZ7wBsOsqF6itlLNi8In4BL1gy-oWrn7CFJI511dRw", f"PL_R4!A:G", value_cutoff=None)

        # payload = []

        # for p in players[1:]:
        #     position = p[5]
        #     player = p[6]

        #     response = client.chat.completions.create(
        #         model="gpt-4",
        #         messages=[
        #             {"role": "system", "content": "You are a terse scouting assistant who wants to provide short, actionable information to decisionmakers who need to know scouting information about baseball players. You prefer hitters with good contact skills and plate discipline. You prefer pitchers with strong fastball traits like high IVB or high spin rate secondaries. You do not need to include newlines or tabs. Your reports for hitters will include hit, power, speed, on-base, and defense. Your reports for pitchers will include pitch breakdowns with velocity, spin rates and command. Your reports do not need to include the player's name or position."},
        #             {"role": "user", "content": f"I need a terse scouting report, around 150 words, about {position} {player}. Offer a comparable current major league player who represents a resonable outcome."},
        #         ]
        #     )

        #     report = player,response.choices[0].message.content

        #     payload.append({"position": position, "player": player, "report": report})

        # with open('reports.csv', 'w', newline='') as csvfile:
        #     fieldnames = ['position', 'player', 'report']
        #     writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        #     writer.writeheader()
        #     for p in payload:
        #         writer.writerow(p)

        # with open('data/pl_top500.csv', 'r') as readfile:
        #     threshold = 0.75
        #     players = csv.DictReader(readfile)
        #     for p in players:
        #         obj = models.Player.objects\
        #             .filter(name__trigram_word_similar=p['Name'])\
        #             .annotate(similarity=TrigramSimilarity('name', p['Name']))\
        #             .filter(similarity__gte=threshold)
        #         player_string = f",{p['Rank']},{p['Position']},{p['Name']},"
        #         if len(obj) == 1:
        #             if not obj[0].team:
        #                 print(f"{obj[0].mlb_id}"+player_string)
        #         else:
        #             print(player_string+"x")



        # with open('data/2023-fg-zipsdc-hitters.csv', 'r', encoding='utf-8-sig') as readfile:
        #     hitters = csv.DictReader(readfile)
        #     print("player\tteam\tage\tpa\twrc\twar")
        #     for h in hitters:
        #         try:
        #             obj = models.Player.objects.get(fg_id=h['PlayerId'])
        #             if not obj.team:
        #                 print(f"{h['Name']}\t{h['Team']}\t{obj.age}\t{h['PA']}\t{h['wRC+']}\t{h['WAR']}")

        #         except models.Player.DoesNotExist:
        #             pass

        # with open('data/2023-fg-zipsdc-pitchers.csv', 'r', encoding='utf-8-sig') as readfile:
        #     pitchers = csv.DictReader(readfile)
        #     print("player\tteam\tage\tip\tst\tera\twar")
        #     for h in pitchers:
        #         try:
        #             obj = models.Player.objects.get(fg_id=h['PlayerId'])
        #             if not obj.team:
        #                 print(f"{h['Name']}\t{h['Team']}\t{obj.age}\t{h['IP']}\t{h['GS']}\t{h['ERA']}\t{h['WAR']}")

        #         except models.Player.DoesNotExist:
        #             pass