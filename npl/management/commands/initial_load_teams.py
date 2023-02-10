from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        teams = []

        def is_team(row):
            if len(row) > 0:
                if "AL: " not in row[0]:
                    if "NL: " not in row[0]:
                        return True
            return False

        teams = utils.get_sheet(settings.ROSTER_SHEET_ID, f"Key!A:V", value_cutoff=None)
        teams = [t for t in teams[39:] if is_team(t)]

        for t in teams:
            """
            ['Absolute Sickos', '', '69', '32', '32', '$41,901,354', '$11,455,475', '$6,600,000']
            """
            team_dict = {}
            team_dict['nickname'] = t[0].split()[-1].strip()
            team_dict['name'] = t[0].strip()
            team_dict['roster_85_man'] = int(t[2])
            team_dict['roster_40_man'] = int(t[3])
            team_dict['roster_30_man'] = int(t[4])
            team_dict['cap_space'] = int(t[5].replace(',', '').replace('$', ''))
            team_dict['reserves'] = int(t[6].replace(',', '').replace('$', ''))
            team_dict['ifa_pool_space'] = int(t[7].replace(',', '').replace('$', ''))

            try:
                team_obj = models.Team.objects.get(nickname=team_dict['nickname'])
                for k,v in team_dict.items():
                    setattr(team_obj, k, v)
                team_obj.save()
                print(f"* {team_obj}")

            except:
                team_obj = models.Team(**team_dict)
                team_obj.save()
                print(f"+ {team_obj}")