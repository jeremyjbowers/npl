from datetime import datetime
import json

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils

class Command(BaseCommand):
    CURRENT_SEASON = utils.get_mlb_season(datetime.today())

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