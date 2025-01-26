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
    def match_ids_from_rosters(self):
        teams = settings.ROSTER_TEAM_IDS

        for team_id, team_abbrev, team_name in teams:

            with open(f"data/rosters/{team_abbrev}_roster.json", "r") as readfile:

                roster = json.loads(readfile.read())

                for player in roster:

                    obj = None
                    fg_id = None
                    mlb_id = None

                    # mlbam has a lot of different ID fields
                    # let's try to get one
                    if player.get('mlbamid'):
                        mlb_id = str(player['mlbamid']).strip()
                        if mlb_id.strip() == "":
                            mlb_id = None

                    if player.get('mlbamid1') and not mlb_id:
                        mlb_id = str(player['mlbamid1']).strip()
                        if mlb_id.strip() == "":
                            mlb_id = None

                    if player.get('mlbamid2') and not mlb_id:
                        mlb_id = str(player['mlbamid2']).strip()
                        if mlb_id.strip() == "":
                            mlb_id = None

                    if player.get('minorbamid') and not mlb_id:
                        mlb_id = str(player['minorbamid']).strip()
                        if mlb_id.strip() == "":
                            mlb_id = None

                    # fg has a lot of different ID fields
                    # let's try and get one
                    if player.get("playerid"):
                        fg_id = str(player["playerid"]).strip()
                        if fg_id.strip() == "":
                            fg_id = None

                    if player.get("playerid1") and not fg_id:
                        fg_id = str(player["playerid1"]).strip()
                        if fg_id.strip() == "":
                            fg_id = None

                    if player.get("playerid2") and not fg_id:
                        fg_id = str(player["playerid2"]).strip()
                        if fg_id.strip() == "":
                            fg_id = None

                    if player.get("oPlayerId") and not fg_id:
                        fg_id = str(player["oPlayerId"]).strip()
                        if fg_id.strip() == "":
                            fg_id = None

                    # player has a minormasterid in the fg_id and needs updating
                    # a player's initial fg_id is a minormaster id like sa12345
                    # but once they get to the majors, they get a new id like 987654
                    # so we need a way to catch these changes and update the old fg_id
                    if player.get("minormasterid", None) and fg_id:
                        obj = models.Player.objects.filter(fg_id=player["minormasterid"])

                        # only do this for players whose fg_id is now different from their minormasterid
                        if player["minormasterid"] != fg_id:
                            if len(obj) == 1:
                                obj = obj[0]
                                obj.fg_id = fg_id
                                obj.save()
                                print(f"+ minormasterid {obj}")


                    # player has an mlbamid but no fg_id yet
                    # since we load players from MLB.com rosters
                    # we will occasionally have debutees show up with mlb_ids but no fg_id
                    # this lets us get stats for them from fg
                    if mlb_id and fg_id:
                        obj = models.Player.objects.filter(mlb_id=mlb_id)

                        if len(obj) == 1:
                            obj = obj[0]

                            # only do this for players missing an fg_id
                            if not obj.fg_id:
                                obj.fg_id = fg_id
                                obj.save()
                                print(f"+ fg_id {obj}")


    def handle(self, *args, **options):
        requests.packages.urllib3.disable_warnings()
        season = utils.get_current_season()
        self.match_ids_from_rosters()