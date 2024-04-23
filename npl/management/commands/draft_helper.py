from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests

from npl import models, utils


class Command(BaseCommand):
    draft_sheet = utils.get_sheet("1UQv_vnBBWUT8BiFRd7tAbvW4COWJ61BNkme7iyzf5po", f"2024 Rule 4!A:AA", value_cutoff=None)
    pref_sheet = utils.get_sheet("1woZ7wBsOsqF6itlLNi8In4BL1gy-oWrn7CFJI511dRw", f"2024 R4!A:T", value_cutoff=None)[1:]
    
    def next_five(self):
        taken_mlbids = [slot[14].strip() for slot in self.draft_sheet if slot[0] !="" and slot[14].strip() != ""][:263]
        available_players = [p for p in self.pref_sheet if p[2].strip() not in taken_mlbids]

        print("Next 5 players >>")
        for p in available_players[:5]:
            print(f"  {p[3]} {p[1]}, MLBID {p[2]}")

    def fill_out_pref_sheet_mlbids(self):
        players = []

        for p in self.pref_sheet:
            if p[1].strip() != "":
                mlb_id = ""
                player_name = p[1]
                search_url = f"https://statsapi.mlb.com/api/v1/people/search?names={p[1]}&sportIds=11,12,13,14,15,5442,16&active=true&hydrate=currentTeam,team"

                try:
                    obj = models.Player.objects.get(name=p[1])
                    mlb_id = obj.mlb_id

                except:

                    try:
                        r = requests.get(search_url, timeout=5)

                        results = r.json().get('people', None)

                        if len(results) == 1:
                            search_player = results[0]
                            mlb_id = search_player['id']


                    except requests.exceptions.ReadTimeout:
                        pass

                    except requests.exceptions.ConnectionError:
                        pass
                players.append((player_name, mlb_id))

        for p in players:
            print(f"{p[0]}\t{p[1]}")

    def handle(self, *args, **options):
        """
        0. identify universe of players
            * load mlbids into my sheet
        1. pref players
            * pitcher, hitter? how to group for selection?
        2. import pref'ed players
        3. compare pref'ed players to taken players
        4. recommend several players to take
        """
        # self.next_five()
        self.fill_out_pref_sheet_mlbids()
