import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
import xlrd

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        os.system('curl -o /tmp/scoresheet.xls "http://www.scoresheet.com/BB_BLcurrent_tabs.xls"')

        sheet = xlrd.open_workbook("/tmp/scoresheet.xls").sheet_by_index(0)
        with open("/tmp/scoresheet.csv",'w',newline="") as writefile:
            col = csv.writer(writefile)
            for row in range(sheet.nrows):
                col.writerow(sheet.row_values(row))

        with open("/tmp/scoresheet.csv", 'r') as readfile:
            players = [p for p in csv.DictReader(readfile) if p['firstName'] != "Really"]

            for p in players:
                print(p)
                obj = None

                clean_first = p['firstName'].split('(')[0].strip()
                clean_last = p['lastName'].split('(')[0].strip()

                try:
                    if p['MLBAM'].split('.')[0].strip() != "":
                        obj = models.Player.objects.get(mlb_id=p['MLBAM'].split('.')[0])
                    elif p['SSBB'].split('.')[0].strip() != "":
                        obj = models.Player.objects.get(scoresheet_id=p['SSBB'].split('.')[0].strip())
                    else:
                        obj = models.Player.objects.get(first_name=clean_first,last_name=clean_last)

                except models.Player.DoesNotExist:
                    if p['MLBAM'].split('.')[0].strip() != "" and p['SSBB'].split('.')[0].strip() != "":
                        obj = models.Player()
                        obj.first_name = clean_first
                        obj.last_name = clean_last
                        obj.mlb_id = p['MLBAM'].split('.')[0].strip()
                        obj.scoresheet_id = p['SSBB'].split('.')[0].strip()

                print(obj)

                if not obj.scoresheet_id and p['SSBB'].split('.')[0].strip() != "":
                    obj.scoresheet_id = p['SSBB'].split('.')[0].strip()

                obj.position = p['pos']
                obj.raw_age = p['age'].split('.')[0].strip()

                if not obj.mlb_org:
                    obj.mlb_org = p['team'].upper()

                if not obj.scoresheet_defense:
                    obj.scoresheet_defense = {}

                if not obj.scoresheet_offense:
                    obj.scoresheet_offense = {}

                for item in ['1B','2B','3B','SS','OF']:
                    if p[item].strip() == '':
                        obj.scoresheet_defense[item] = None
                    else:
                        obj.scoresheet_defense[item] = int(float(p[item].split('.')[0].strip())*100.0)

                for item in ['BAvR','OBvR','SLvR','BAvL','OBvL','SLvL']:
                    if p[item].strip() == '':
                        obj.scoresheet_offense[item] = None
                    else:
                        obj.scoresheet_offense[item] = int(p[item].split('.')[0].strip())

                obj.save()