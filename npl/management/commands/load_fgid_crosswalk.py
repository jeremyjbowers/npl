import ujson as json

from django.core.management.base import BaseCommand, CommandError

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        not_in_db = []
        with open('data/fgid_crosswalk.json', 'r') as readfile:
            players = json.loads(readfile.read())

            for p in players:
                try:
                    obj = models.Player.objects.get(mlb_id=p['mlb_id'])
                    if not obj.fg_id:
                        obj.fg_id = p['fg_id']
                        obj.save()
                        print(f"* {obj}")

                except models.Player.DoesNotExist:
                    obj = models.Player(mlb_id=p['mlb_id'], fg_id=p['fg_id'])
                    obj.update_mlb_info()
                    obj.save()
