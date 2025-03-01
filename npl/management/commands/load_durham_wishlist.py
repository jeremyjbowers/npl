import time

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
import ujson as json

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        
        new_players = []

        def handle_num(possible_num):
            if possible_num:
                if possible_num.strip() != "":
                    try:
                        return int(possible_num)
                    except:
                        pass
            return None

        team = models.Team.objects.get(short_name="Tobacconists")        
        wishlist,created = models.Wishlist.objects.get_or_create(team=team)
        wishlist.save()

        sheet = utils.get_sheet("1woZ7wBsOsqF6itlLNi8In4BL1gy-oWrn7CFJI511dRw", "2025 R4", value_cutoff=None)
        headers = sheet[0]
        for row in sheet[1:]:
            player = dict(zip(headers, row))

            try:
                p_obj = models.Player.objects.get(mlb_id=player['mlbid'])
                wlp_obj, created = models.WishlistPlayer.objects.get_or_create(player=p_obj, wishlist=wishlist)
                wlp_obj.note = player['report']
                wlp_obj.rank = handle_num(player.get('RANK', None))
                wlp_obj.player_fv = handle_num(player.get('ba', None))
                wlp_obj.player_risk = handle_num(player.get('risk', None))

                if player.get('mmf', None):
                    if player['mmf'].strip() == "x":
                        wlp_obj.interesting = True

                wlp_obj.save()

            except models.Player.DoesNotExist:
                new_players.append(player)


        with open('new_player.json', 'w') as writefile:
            writefile.write(json.dumps(new_players))