from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from nameparser import HumanName

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        fa_players = utils.get_sheet(settings.LEAGUE_SHEET_ID, f"Free Agents, Waivers, Opt-Outs!A12:J1004", value_cutoff=None)

        for p in fa_players:
            if len(p) > 3:
                player_dict = {}

                player_dict['raw_name'] = p[0]

                parsed_name = HumanName(p[0])

                player_dict['first_name'] = parsed_name.first
                if parsed_name.middle:
                    player_dict['first_name'] += f" {parsed_name.middle}"

                player_dict['last_name'] = parsed_name.last
                if parsed_name.suffix:
                    player_dict['last_name'] += f" {parsed_name.suffix}"

                player_dict['scoresheet_id'] = None
                player_dict['mlb_id'] = None
    
                if p[1].strip() != "" and p[1].strip() != "-":
                    player_dict['scoresheet_id'] = p[1].strip()
    
                if p[2].strip() != "" and p[2].strip() != "-":
                    player_dict['mlb_id'] = p[2].strip()

                if player_dict['mlb_id']:
                    player_dict['position'] = p[3].strip()
                    player_dict['mlb_org'] = p[4].strip()

                    player_dict['mls_time'] = None
                    player_dict['mls_year'] = None
                    player_dict['options'] = None
                    player_dict['status'] = None

                    if "." in p[5]:
                        player_dict['mls_time'] = float(p[5])

                    elif len(p[5]) == 4:
                        player_dict['mls_year'] = int(p[5])

                    try:
                        player_dict['options'] = p[6].strip()
                    except IndexError:
                        pass

                    try:
                        player_dict['status'] = p[7].strip()
                    except IndexError:
                        pass

                    try:
                        obj = models.Player.objects.get(mlb_id=player_dict['mlb_id'])
                        for k,v in player_dict.items():
                            setattr(obj,k,v)
                        obj.save()
                        print(f"* {obj}")

                    except models.Player.DoesNotExist:
                        obj = models.Player(**player_dict)
                        obj.save()
                        print(f"+ {obj}")

            