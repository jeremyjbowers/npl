from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        models.Player.objects.filter(team__isnull=False).update(team=None)
        models.Player.objects.all().update(is_roster_30_man=False)
        models.Player.objects.all().update(is_roster_40_man=False)

        ROSTER_HEADERS = [
            ("STARTING PITCHERS", "is_roster_30_man"),
            ("RELIEF PITCHERS", "is_roster_30_man"),
            ("INFIELDERS", "is_roster_30_man"),
            ("OUTFIELDERS", "is_roster_30_man"),
            ("7-DAY INJURED LIST", "is_roster_7_day_il"),
            ("56-DAY INJURED LIST", "is_roster_56_day_il"),
            ("END OF SEASON INJURED LIST", "is_roster_eos_il"),
            ("RESTRICTED LIST", "is_roster_restricted"),
            ("TRIPLE-A", "is_roster_aaa"),
            ("DOUBLE-A", "is_roster_aa"),
            ("SINGLE-A", "is_roster_a"),
            ("ON OPTION", "is_roster_aaa_option"),
            ("ASSIGNED OUTRIGHT", "is_roster_aaa_outright"),
            ("FOREIGN", "is_roster_aaa_foreign"),
            ("RETIRED", "is_roster_aaa_retired"),
            ("NON-ROSTER", "is_roster_aaa_nri")
        ]

        CROSSWALK = {}

        # CROSSWALK = {
        #     "Duno, Alfredo": "806957",
        #     "Valdez, Derniche": "806961",
        #     "Rodriguez, Jose": "800412",
        #     "Vargas, Marco": "804614",
        #     "Weiss, Zack": "592848",
        #     "Figuereo, Gleider": "699213",
        #     "Guerrero, Brailer": "806967",
        #     "Burrowes, Ryan": "802018",
        #     "Morales, Luis": "806960",
        #     "Guerrero, Pablo": "808326",
        #     "Francisca, Welbyn": "806988",
        #     "Cespedes, Yoelin": "806985",
        #     "Pegero, Antony": "803433",
        #     "Cepeda, Angel": "806980",
        #     "Lantigua, Arnaldo": "806984",
        #     "Espinoza, Ludwig": "806968",
        #     "Fleury, Jose": "800067",
        #     "Valdez, Luis": "692835",
        #     "De Los Santos, Anderson": "698945",
        #     "Pan, Wen-Hui": "808207",
        #     "Gonzalez, Cesar": "800177",
        #     "Mateo, Carlos": "801786",
        #     "Pachardo, Bladimir": "808097",
        #     "Di Turi, Filippo": "806995",
        # }

        # for t in models.Team.objects.all():
        for t in models.Team.objects.all():
            current_header = None
            players = []
            print(t)
            team_players = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t.tab_id}!A:V", value_cutoff=None)

            for row in team_players:
                if row == []:
                    continue
                if row == ['', 'FINANCIALS']:
                    current_header = None
                    break

                for header,x in ROSTER_HEADERS:
                    if header in row[1]:
                        current_header = header
                        
                if row[0].strip() in ["", "x", "-", "1"]:
                    if "," in row[1]:
                        player_dict = {
                            "is_roster_7_day_il": False,
                            "is_roster_56_day_il": False,
                            "is_roster_eos_il": False,
                            "is_roster_restricted": False,
                            "is_roster_aaa": False,
                            "is_roster_aaa_option": False,
                            "is_roster_aaa_outright": False,
                            "is_roster_aaa_retired": False,
                            "is_roster_aaa_nri": False,
                            "is_roster_30_man": False,
                            "is_roster_40_man": False,
                            "is_roster_aa": False,
                            "is_roster_a": False,
                        }

                        if row[0] == "1":
                            player_dict['is_roster_40_man'] = True
                            
                        for header, key in ROSTER_HEADERS:
                            if current_header == header:
                                player_dict[key] = True
                                player_dict['npl_status'] = key

                        players.append(utils.format_player_row(row, t, player_dict))

                
            for idx, p in enumerate(players):
                """
                debug
                """
                player_obj = None
                try:

                    if not p['mlb_id'] and not p['scoresheet_id']:
                        if CROSSWALK.get(p['raw_name'], None):
                            p['mlb_id'] = CROSSWALK.get(p['raw_name'], None)
                    
                    if p['mlb_id'] and p['mlb_id'] != "-":
                        player_obj = models.Player.objects.get(mlb_id=p['mlb_id'])

                    elif p['scoresheet_id'] and p['scoresheet_id'] != "-":
                        player_obj = models.Player.objects.get(scoresheet_id=p['scoresheet_id'])

                    if player_obj:
                        for k,v in p.items():
                            if k != "mlb_id":
                                setattr(player_obj, k, v)

                        player_obj.team = t
                        player_obj.save()
                        # print(f"* {player_obj}")

                except models.Player.DoesNotExist:
                    pass

                if not player_obj:
                    if p.get('mlb_id', None):
                        p['mlb_id'] = int(p['mlb_id'])
                        player_obj = models.Player(**p)
                        player_obj.save()
                        print(f"+ {player_obj}")

                    else:
                        player_obj = models.Player(**p)
                        player_obj.set_name()

                        search_url = f"https://statsapi.mlb.com/api/v1/people/search?names={player_obj.name}&sportIds=11,12,13,14,15,5442,16&active=true&hydrate=currentTeam,team"
                        # print(search_url)

                        r = requests.get(search_url, timeout=5)
                        results = r.json().get('people', None)

                        if len(results) == 1:
                            pl = results[0]

                            player_obj.mlb_id = pl['id']
                            player_obj.birthdate = pl['birthDate']

                            try:
                                npl_obj = models.Player.objects.get(mlb_id=pl['id'])

                            except models.Player.DoesNotExist:
                                player_obj.save()
                                print(f"+ {player_obj}")

                        else:
                            print(f'\t"{p["raw_name"]}": "",')

        for p in models.Player.objects.filter(last_name=""):
            p.first_name = p.raw_name.split(', ')[1].strip()
            p.last_name = p.raw_name.split(', ')[0].strip()
            p.save()

        for p in models.Player.objects.all():
            try:
                p.first_name = p.first_name.strip()
                p.last_name = p.last_name.strip()
                p.name = p.name.strip()
                p.save()

            except AttributeError:
                pass