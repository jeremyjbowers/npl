from datetime import datetime
import json

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils

class Command(BaseCommand):
    CURRENT_SEASON = None
    def handle(self, *args, **options):
        self.nuke_stats()
        self.get_stats()
        self.CURRENT_SEASON = utils.get_mlb_season(datetime.today())

        # milb_bat_url = f"https://www.fangraphs.com/api/leaders/minor-league/data?pos=all&level=0&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32,33&stats=bat&qual=0&type=c%2C6%2C-1%2C312%2C305%2C309%2C306%2C307%2C308%2C310%2C311%2C-1%2C23%2C315%2C-1%2C38%2C316%2C-1%2C50%2C317%2C7%2C8%2C9%2C10%2C11%2C12%2C13%2C14%2C21%2C23%2C34%2C35%2C37%2C38%2C39%2C40%2C41%2C50%2C52%2C57%2C58%2C61%2C62%2C5&team=&season={season}&seasonEnd={season}&org=&ind=0&splitTeam=false"

        # milb_pit_url = f"https://www.fangraphs.com/api/leaders/minor-league/data?pos=all&level=0&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32,33&stats=pit&qual=0&type=c%2C4%2C5%2C11%2C7%2C8%2C13%2C-1%2C24%2C19%2C15%2C18%2C36%2C37%2C40%2C43%2C44%2C48%2C51%2C-1%2C240%2C-1%2C6%2C332%2C45%2C62%2C122%2C-1%2C59%2C17%2C301%2C302%2C303%2C117%2C118%2C119&team=&season={season}&seasonEnd={season}&org=&ind=0&splitTeam=false"

        # mlb_bat_url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=bat&lg=all&qual=0&season={season}&season1={season}&startdate={season}-01-01&enddate={season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C6%2C-1%2C312%2C305%2C309%2C306%2C307%2C308%2C310%2C311%2C-1%2C23%2C315%2C-1%2C38%2C316%2C-1%2C50%2C317%2C7%2C8%2C9%2C10%2C11%2C12%2C13%2C14%2C21%2C23%2C34%2C35%2C37%2C38%2C39%2C40%2C41%2C50%2C52%2C57%2C58%2C61%2C62%2C5&sortdir=desc&sortstat=Events"
        # mlb_pit_url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=pit&lg=all&qual=2&season={season}&season1={season}&startdate={season}-01-01&enddate={season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C4%2C5%2C11%2C7%2C8%2C13%2C-1%2C24%2C19%2C15%2C18%2C36%2C37%2C40%2C43%2C44%2C48%2C51%2C-1%2C240%2C-1%2C6%2C332%2C45%2C62%2C122%2C-1%2C59%2C17%2C301%2C302%2C303%2C117%2C118%2C119&sortdir=desc&sortstat=SO"

        # urls = [milb_bat_url, milb_pit_url, mlb_bat_url, mlb_pit_url]

        # for url in urls:
        #     print(url)
        #     rows = requests.get(url).json()

        #     if isinstance(rows, dict):
        #         rows = rows['data']

        #     print(rows[0].keys())



    KEYS = {
        "hitting": ['plateAppearances', 'totalBases', 'leftOnBase', 'sacBunts', 'sacFlies', 'babip', 'extraBaseHits', 'hitByPitch', 'gidp', 'gidpOpp', 'numberOfPitches', 'pitchesPerPlateAppearance', 'walksPerPlateAppearance', 'strikeoutsPerPlateAppearance', 'homeRunsPerPlateAppearance', 'walksPerStrikeout', 'reachedOnError', 'walkOffs', 'flyOuts', 'totalSwings', 'swingAndMisses', 'ballsInPlay', 'popOuts', 'lineOuts', 'groundOuts', 'flyHits', 'popHits', 'lineHits', 'groundHits', 'gamesPlayed', 'airOuts', 'runs', 'doubles', 'triples', 'homeRuns', 'strikeOuts', 'baseOnBalls', 'intentionalWalks', 'hits', 'avg', 'atBats', 'obp', 'slg', 'ops', 'caughtStealing', 'stolenBases', 'stolenBasePercentage', 'groundIntoDoublePlay', 'rbi', 'groundOutsToAirouts', 'catchersInterference', 'atBatsPerHomeRun'],
        "pitching": ['winningPercentage', 'runsScoredPer9', 'battersFaced', 'babip', 'obp', 'slg', 'ops', 'strikeoutsPer9', 'baseOnBallsPer9', 'homeRunsPer9', 'hitsPer9', 'strikesoutsToWalks', 'inheritedRunners', 'inheritedRunnersScored', 'bequeathedRunners', 'bequeathedRunnersScored', 'stolenBases', 'caughtStealing', 'qualityStarts', 'gamesFinished', 'doubles', 'triples', 'gidp', 'gidpOpp', 'wildPitches', 'balks', 'pickoffs', 'totalSwings', 'swingAndMisses', 'ballsInPlay', 'runSupport', 'strikePercentage', 'pitchesPerInning', 'pitchesPerPlateAppearance', 'walksPerPlateAppearance', 'strikeoutsPerPlateAppearance', 'homeRunsPerPlateAppearance', 'walksPerStrikeout', 'iso', 'flyOuts', 'popOuts', 'lineOuts', 'groundOuts', 'flyHits', 'popHits', 'lineHits', 'groundHits', 'gamesPlayed', 'gamesStarted', 'airOuts', 'runs', 'homeRuns', 'strikeOuts', 'baseOnBalls', 'intentionalWalks', 'hits', 'hitByPitch', 'avg', 'atBats', 'stolenBasePercentage', 'groundIntoDoublePlay', 'numberOfPitches', 'era', 'inningsPitched', 'wins', 'losses', 'saves', 'saveOpportunities', 'holds', 'blownSaves', 'earnedRuns', 'whip', 'outs', 'gamesPitched', 'completeGames', 'shutouts', 'strikes', 'hitBatsmen', 'totalBases', 'groundOutsToAirouts', 'winPercentage', 'strikeoutWalkRatio', 'strikeoutsPer9Inn', 'walksPer9Inn', 'hitsPer9Inn', 'catchersInterference', 'sacBunts', 'sacFlies'],
    }

    def nuke_stats(self):
        models.Player.objects.update(stats=[])

    def get_api_json(self, url):
        r = requests.get(url)
        return r.json()['stats']

    def parse_stats(self, stat_type, players, keys, l):
        for p in players:
            try:
                obj = models.Player.objects.get(mlb_id=p['playerId'])
                if l[0] == 1:
                    obj.is_mlb_eligible = True
                league = l[1]

                if not obj.stats:
                    obj.stats = []

                stat_dict = {}
                for k,v in p.items():
                    if k in keys:
                        stat_dict[k] = v

                stat_dict['season'] = self.CURRENT_SEASON
                stat_dict['level'] = l[1]

                obj.stats.append(stat_dict)
                
                if stat_type == "hitting":
                    obj.position = p['positionAbbrev']

                obj.save()
                print(f"* {obj}")
            
            except models.Player.DoesNotExist:
                pass

    def get_stats(self):
        for side in ["hitting", "pitching"]:
            for l in settings.LEVELS:
                slug = f"{l[1]}"

                url = f"https://bdfed.stitch.mlbinfra.com/bdfed/stats/player?stitch_env=prod&season={self.CURRENT_SEASON}&sportId={l[0]}&stats=season&group={side}&gameType=R&limit=2500&offset=0&sortStat=onBasePlusSlugging&order=desc&playerPool=ALL"
                
                keys = self.KEYS[side]
                players = self.get_api_json(url)
                self.parse_stats(side, players, keys, l)


    def handle(self, *args, **options):
        self.nuke_stats()
        self.get_stats()