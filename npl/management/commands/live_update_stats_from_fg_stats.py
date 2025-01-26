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

    def set_mlb_hitter_season(self):
        with open(f'data/{self.season}/fg_mlb_bat.json', 'r') as readfile:
            rows = json.loads(readfile.read())

            for row in rows:
                stats_dict = {}

                stats_dict["year"] = self.season
                stats_dict["type"] = "majors"
                stats_dict["level"] = "mlb"
                stats_dict["side"] = "hit"
                stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}_{stats_dict['side']}"

                obj = models.Player.objects.filter(
                    fg_id=row['playerid']
                )

                if obj.count() > 0:
                    obj = obj[0]

                    stats_dict["hits"] = utils.to_int(row['H'])
                    stats_dict["2b"] = utils.to_int(row['2B'])
                    stats_dict["3b"] = utils.to_int(row['3B'])
                    stats_dict["hr"] = utils.to_int(row['HR'])
                    stats_dict["sb"] = utils.to_int(row['SB'])
                    stats_dict["runs"] = utils.to_int(row['R'])
                    stats_dict["rbi"] = utils.to_int(row['RBI'])
                    stats_dict["wrc_plus"] = utils.to_int(row['wRC+'])
                    stats_dict["plate_appearances"] = utils.to_int(row['PA'])
                    stats_dict["ab"] = utils.to_int(row['AB'])

                    stats_dict["avg"] = utils.to_float(row['AVG'])
                    stats_dict["xavg"] = utils.to_float(row['xAVG'])
                    stats_dict["obp"] = utils.to_float(row['OBP'])
                    stats_dict["slg"] = utils.to_float(row['SLG'])
                    stats_dict["xslg"] = utils.to_float(row['xSLG'])
                    stats_dict["babip"] = utils.to_float(row['BABIP'])
                    stats_dict["iso"] = utils.to_float(row['ISO'])
                    stats_dict["k_pct"] = utils.to_float(row["K%"], default=0.0) * 100.0
                    stats_dict["bb_pct"] = utils.to_float(row["BB%"], default=0.0) * 100.0
                    stats_dict["xwoba"] = utils.to_float(row['xwOBA'])

                    obj.set_stats(stats_dict)
                    obj.save()


    def set_mlb_pitcher_season(self):
        with open(f'data/{self.season}/fg_mlb_pit.json', 'r') as readfile:
            rows = json.loads(readfile.read())

            for row in rows:
                stats_dict = {}

                stats_dict["year"] = self.season
                stats_dict["type"] = "majors"
                stats_dict["level"] = "mlb"
                stats_dict["side"] = "pitch"
                stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}_{stats_dict['side']}"

                obj = models.Player.objects.filter(
                    fg_id=row['playerid']
                )

                if obj.count() > 0:
                    obj = obj[0]

                    stats_dict["g"] = utils.to_int(row['G'])
                    stats_dict["gs"] = utils.to_int(row['GS'])
                    stats_dict["k"] = utils.to_int(row['SO'])
                    stats_dict["bb"] = utils.to_int(row['BB'])
                    stats_dict["ha"] = utils.to_int(row['H'])
                    stats_dict["hra"] = utils.to_int(row['HR'])
                    stats_dict["ip"] = utils.to_float(row['IP'])
                    stats_dict["k_9"] = utils.to_float(row['K/9'])
                    stats_dict["bb_9"] = utils.to_float(row['BB/9'])
                    stats_dict["hr_9"] = utils.to_float(row['HR/9'])
                    stats_dict["lob_pct"] = (
                        utils.to_float(row["LOB%"], default=0.0) * 100.0
                    )
                    stats_dict["gb_pct"] = utils.to_float(row["GB%"], default=0.0) * 100.0
                    stats_dict["hr_fb"] = utils.to_float(row['HR/FB'])
                    stats_dict["era"] = utils.to_float(row['ERA'])
                    stats_dict["fip"] = utils.to_float(row['FIP'])
                    stats_dict["xfip"] = utils.to_float(row['xFIP'])
                    stats_dict["siera"] = utils.to_float(row['SIERA'])
                    stats_dict['xERA'] = utils.to_float(row['xERA'])
                    stats_dict['sp_stuff'] = utils.to_float(row['sp_stuff'])
                    stats_dict['sp_location'] = utils.to_float(row['sp_location'])
                    stats_dict['sp_pitching'] = utils.to_float(row['sp_pitching'])
                    stats_dict["er"] = utils.to_float(row['ER'])
                    stats_dict["k_9+"] = utils.to_int(row['K/9+'])
                    stats_dict["bb_9+"] = utils.to_int(row['BB/9+'])
                    stats_dict["era-"] = utils.to_int(row['ERA-'])
                    stats_dict["fip-"] = utils.to_int(row['FIP-'])
                    stats_dict["xfip-"] = utils.to_int(row['xFIP-'])

                    obj.set_stats(stats_dict)
                    obj.save()

    def set_minor_season(self):
        for side in ['bat', 'pit']:
            with open(f'data/{self.season}/fg_milb_{side}.json', 'r') as readfile:
                rows = json.loads(readfile.read())

                for player in rows:
                    fg_id = player["playerids"]
                    name = player["PlayerName"]
                    p = models.Player.objects.filter(fg_id=fg_id)

                    if len(p) == 1:
                        obj = p[0]

                        stats_dict = {}
                        stats_dict['side'] = side
                        stats_dict["type"] = "minors"
                        stats_dict["level"] = player["aLevel"]
                        stats_dict["year"] = self.season
                        stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}_{stats_dict['side']}"

                        if side == "bat":
                            stats_dict["side"] = "hit"
                            stats_dict["hits"] = utils.to_int(player["H"])
                            stats_dict["2b"] = utils.to_int(player["2B"])
                            stats_dict["3b"] = utils.to_int(player["3B"])
                            stats_dict["hr"] = utils.to_int(player["HR"])
                            stats_dict["sb"] = utils.to_int(player["SB"])
                            stats_dict["runs"] = utils.to_int(player["R"])
                            stats_dict["rbi"] = utils.to_int(player["RBI"])
                            stats_dict["avg"] = utils.to_float(player["AVG"])
                            stats_dict["obp"] = utils.to_float(player["OBP"])
                            stats_dict["slg"] = utils.to_float(player["SLG"])
                            stats_dict["babip"] = utils.to_float(player["BABIP"])
                            stats_dict["wrc_plus"] = utils.to_int(player["wRC+"])
                            stats_dict["plate_appearances"] = utils.to_int(player["PA"])
                            stats_dict["iso"] = utils.to_float(player["ISO"])
                            stats_dict["k_pct"] = utils.to_float(player["K%"], default=0.0) * 100.0
                            stats_dict["bb_pct"] = utils.to_float(player["BB%"], default=0.0) * 100.0
                            stats_dict["woba"] = utils.to_float(player["wOBA"])

                        if side == "pit":
                            stats_dict["side"] = "pitch"
                            stats_dict["g"] = utils.to_int(player["G"])
                            stats_dict["gs"] = utils.to_int(player["GS"])
                            stats_dict["k"] = utils.to_int(player["SO"])
                            stats_dict["bb"] = utils.to_int(player["BB"])
                            stats_dict["ha"] = utils.to_int(player["H"])
                            stats_dict["hra"] = utils.to_int(player["HR"])
                            stats_dict["ip"] = utils.to_float(player["IP"])
                            stats_dict["k_9"] = utils.to_float(player["K/9"])
                            stats_dict["bb_9"] = utils.to_float(player["BB/9"])
                            stats_dict["hr_9"] = utils.to_float(player["HR/9"])
                            stats_dict["lob_pct"] = (
                                utils.to_float(player["LOB%"], default=0.0) * 100.0
                            )
                            stats_dict["gb_pct"] = utils.to_float(player["GB%"], default=0.0) * 100.0
                            stats_dict["hr_fb"] = utils.to_float(player["HR/FB"])
                            stats_dict["era"] = utils.to_float(player["ERA"])
                            stats_dict["fip"] = utils.to_float(player["FIP"])
                            stats_dict["xfip"] = utils.to_float(player["xFIP"])

                        obj.set_stats(stats_dict)
                        obj.save()


    def handle(self, *args, **options):
        self.set_minor_season()
        self.set_mlb_hitter_season()
        self.set_mlb_pitcher_season()

