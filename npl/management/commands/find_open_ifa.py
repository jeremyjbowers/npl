from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import ujson as json

from nameparser import HumanName

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        free_ifa = []

        with open('international.json', 'r') as readfile:
            ifas = json.loads(readfile.read())

            ifas = [i for i in ifas if i.get('mlb_id', None)]

            for i in ifas:
                
                try:
                    obj = models.Player.objects.get(mlb_id=i['mlb_id'])

                except models.Player.DoesNotExist:
                    obj = models.Player()
                    obj.birthdate = i['birthdate']
                    obj.raw_name = i['name']
                    obj.mlb_org = i['team']
                    obj.mlb_id = i['mlb_id']
                    obj.position = i['position']
                    obj.save()

                if not obj.team:
                    free_ifa.append({"position": obj.position, "mlb_org": obj.mlb_org, "name": obj.name, "url": f"https://www.milb.com/player/{obj.mlb_id}" })

        for i in free_ifa:
            print(f"{i['name']},{i['position']},{i['mlb_org']},{i['url']}")