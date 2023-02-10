from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils
from users.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):

        owners = []

        def is_owner(row):
            return True

        owners = utils.get_sheet(settings.LEAGUE_SHEET_ID, f"Team Owners!A:H", value_cutoff=None)
        owners = [o for o in owners[8:] if is_owner(o)]

        for o in owners:
            """
            ['Defenestrations of Prague', 'Evan Brunell', '2009', 'evanbrunell@gmail.com', '@evanbrunell', '774-230-5851 (text only)', 'Worcester, MA', 'Communications Strategist, Worcester Polytechnic Institute']
            """

            owner_dict = {}
            user_dict = {"email": None}
            team_name = o[0].strip()
            owner_dict['name'] = o[1].strip()
            owner_dict['first_year'] = int(o[2].strip())

            if len(o) > 3:
                user_dict['email'] = o[3].strip()

            if len(o) > 6:
                if o[4] != "":
                    owner_dict['twitter'] = o[4].strip()

                if o[5] != "":
                    owner_dict['phone'] = o[5].strip()

                if o[6] != "":
                    owner_dict['hometown'] = o[6].strip()
            if len(o) > 7:
                if o[7] != "":
                    owner_dict['bio'] = o[7].strip()

            user_obj = None
            owner_obj = None
            team_obj = None

            if user_dict['email']:
                try:
                    user_obj = User.objects.get(email=user_dict['email'])
                except:
                    user_obj = User(email=user_dict['email'])
                    user_obj.save()
                    print(user_obj)

            try:
                owner_obj = models.Owner.objects.get(name=owner_dict['name'])
                for k,v in owner_dict.items():
                    setattr(owner_obj, k, v)
                if user_obj:
                    owner_obj.user = user_obj
                owner_obj.save()
                print(f"* {owner_obj}")

            except:
                owner_obj = models.Owner(**owner_dict)
                if user_obj:
                    owner_obj.user = user_obj
                owner_obj.save()
                print(f"+ {owner_obj}")

            if owner_obj:
                team_obj = models.Team.objects.get(name=team_name)
                team_obj.owners.add(owner_obj)
                team_obj.save()
