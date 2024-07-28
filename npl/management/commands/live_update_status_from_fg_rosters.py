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

    def handle(self, *args, **options):
        teams = settings.ROSTER_TEAM_IDS

        models.Player.objects.all().update(fg_role_type=None, fg_is_injured=False, fg_role=None, fg_is_starter=False, fg_is_bench=False, fg_injury_description=None, fg_is_mlb40man=False)

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

                    if fg_id:
                        try:
                            obj = models.Player.objects.get(fg_id=fg_id)
                        except:
                            pass

                    if mlb_id and not obj:
                        try:
                            obj = models.Player.objects.get(mlb_id=mlb_id)
                        except:
                            pass

                    if not obj:
                        print(player)

                    if obj:
                        obj.fg_is_injured = False
                        obj.fg_role = None
                        obj.fg_is_starter = False
                        obj.fg_is_bench = False
                        obj.fg_injury_description = None
                        obj.fg_is_mlb40man = False
                        obj.fg_role_type = None

                        if player.get("mlevel", None):
                            obj.fg_role = player["mlevel"]
                        
                        elif player.get("role", None):
                            if player["role"].strip() != "":
                                obj.fg_role = player["role"]

                        if obj.fg_role == "MLB":
                            obj.fg_is_mlb40man = True

                        if player.get('type', None):
                            if player["type"] == "mlb-bp":
                                obj.fg_is_bullpen = True

                            if player["type"] == "mlb-sp":
                                obj.fg_is_starter = True

                            if player["type"] == "mlb-bn":
                                obj.fg_is_bench = True

                            if player["type"] == "mlb-sl":
                                obj.fg_is_starter = True

                            obj.fg_role_type = player['type']

                            # if "il" in player["type"]:
                            #     obj.fg_is_injured = True

                            # if "sp" in player['type']:
                            #     obj.fg_role_type = "SP"

                            # if "rp" in player['type']:
                            #     obj.fg_role_type = "RP"

                            # if "bp" in player['type']:
                            #     obj.fg_role_type = "RP"

                            # if "pp" in player['type']:
                            #     obj.fg_role_type = "PP"

                            # if "bn" in player['type']:
                            #     obj.fg_role_type = "BN"

                            # if "il" in player['type']:
                            #     obj.fg_role_type = "IL"

                        obj.fg_injury_description = player.get("injurynotes", None)

                        if player.get('roster40', None):
                            if player["roster40"] == "Y":
                                obj.fg_is_mlb40man = True

                        obj.save()
                        print(obj)