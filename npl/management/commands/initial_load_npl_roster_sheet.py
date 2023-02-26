from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        for t in models.Team.objects.all():
            team_players = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t.tab_id}!A:V", value_cutoff=None)
            team_players = [utils.format_player_row(row, t) for row in team_players if utils.is_player(row)]

            for p in team_players:
                player_obj = None
                try:
                    if p['mlb_id'] and p['mlb_id'] != "-":
                        player_obj = models.Player.objects.get(mlb_id=p['mlb_id'])

                    elif p['scoresheet_id'] and p['scoresheet_id'] != "-":
                        player_obj = models.Player.objects.get(scoresheet_id=p['scoresheet_id'])

                    for k,v in p.items():
                        if k != "mlb_id":
                            setattr(player_obj, k, v)

                    player_obj.team = t
                    player_obj.save()
                    print(f"* {player_obj}")

                except models.Player.DoesNotExist:
                    pass

                if not player_obj:
                    if p['mlb_id'].strip() != "" and p['mlb_id'].strip() != "-":
                        player_obj = models.Player(**p)
                        player_obj.save()
                        print(f"+ {player_obj}")
                    else:
                        print(p)

        for p in models.Player.objects.filter(last_name=""):
            p.first_name = p.raw_name.split(', ')[1].strip()
            p.last_name = p.raw_name.split(', ')[0].strip()
            p.save()

            print(p)

        for p in models.Player.objects.all():
            p.first_name = p.first_name.strip()
            p.last_name = p.last_name.strip()
            p.name = p.name.strip()
            p.save()