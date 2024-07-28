import csv
import json
import os
from decimal import Decimal

from bs4 import BeautifulSoup
from dateutil.parser import parse
from django.apps import apps
from django.db import connection
from django.db.models import Avg, Sum, Count
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import requests

from npl import models, utils


class Command(BaseCommand):
    season = utils.get_current_season()

    def get_fg_major_hitter_season(self):
        url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=bat&lg=all&qual=0&season={self.season}&season1={self.season}&startdate={self.season}-01-01&enddate={self.season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C6%2C-1%2C312%2C305%2C309%2C306%2C307%2C308%2C310%2C311%2C-1%2C23%2C315%2C-1%2C38%2C316%2C-1%2C50%2C317%2C7%2C8%2C9%2C10%2C11%2C12%2C13%2C14%2C21%2C23%2C34%2C35%2C37%2C38%2C39%2C40%2C41%2C50%2C52%2C57%2C58%2C61%2C62%2C5&sortdir=desc&sortstat=Events"
        rows = requests.get(url).json()['data']

        with open(f'data/{self.season}/fg_mlb_bat.json', 'w') as writefile:
            writefile.write(json.dumps(rows))

    def get_fg_major_pitcher_season(self):
        url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=pit&lg=all&qual=2&season={self.season}&season1={self.season}&startdate={self.season}-01-01&enddate={self.season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C4%2C5%2C11%2C7%2C8%2C13%2C-1%2C24%2C19%2C15%2C18%2C36%2C37%2C40%2C43%2C44%2C48%2C51%2C-1%2C240%2C-1%2C6%2C332%2C45%2C62%2C122%2C-1%2C59%2C17%2C301%2C302%2C303%2C117%2C118%2C119&sortdir=desc&sortstat=SO"
        rows = requests.get(url).json()['data']

        with open(f'data/{self.season}/fg_mlb_pit.json', 'w') as writefile:
            writefile.write(json.dumps(rows))

    def get_fg_minor_season(self):
        headers = {"accept": "application/json"}
        players = {"bat": [], "pit": []}

        for k, v in players.items():
            url = f"https://www.fangraphs.com/api/leaders/minor-league/data?pos=all&level=0&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&stats={k}&qual=0&type=0&team=&season={self.season}&seasonEnd={self.season}&org=&ind=0&splitTeam=false"
            r = requests.get(url, verify=False)
            players[k] += r.json()

        for k, v in players.items():
                with open(f'data/{self.season}/fg_milb_{k}.json', 'w') as writefile:
                    writefile.write(json.dumps(v))

    def handle(self, *args, **options):
        self.get_fg_major_hitter_season()
        self.get_fg_major_pitcher_season()
        self.get_fg_minor_season()
