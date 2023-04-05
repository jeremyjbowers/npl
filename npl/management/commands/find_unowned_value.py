import csv

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import ujson as json

from nameparser import HumanName

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        with open('data/2023-fg-zipsdc-hitters.csv', 'r', encoding='utf-8-sig') as readfile:
            hitters = csv.DictReader(readfile)
            print("player\tteam\tage\tpa\twrc\twar")
            for h in hitters:
                try:
                    obj = models.Player.objects.get(fg_id=h['PlayerId'])
                    if not obj.team:
                        print(f"{h['Name']}\t{h['Team']}\t{obj.age}\t{h['PA']}\t{h['wRC+']}\t{h['WAR']}")

                except models.Player.DoesNotExist:
                    pass

        with open('data/2023-fg-zipsdc-pitchers.csv', 'r', encoding='utf-8-sig') as readfile:
            pitchers = csv.DictReader(readfile)
            print("player\tteam\tage\tip\tst\tera\twar")
            for h in pitchers:
                try:
                    obj = models.Player.objects.get(fg_id=h['PlayerId'])
                    if not obj.team:
                        print(f"{h['Name']}\t{h['Team']}\t{obj.age}\t{h['IP']}\t{h['GS']}\t{h['ERA']}\t{h['WAR']}")

                except models.Player.DoesNotExist:
                    pass