import time

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        models.Player.objects.filter(team__isnull=False).update(team=None)
        models.Player.objects.all().update(roster_30man=False)
        models.Player.objects.all().update(roster_40man=False)

        ROSTER_HEADERS = [
            ("7-DAY INJURED LIST", "roster_7dayIL"),
            ("56-DAY INJURED LIST", "roster_56dayIL"),
            ("END OF SEASON INJURED LIST", "roster_eosIL"),
            ("RESTRICTED LIST", "roster_restricted"),
            ("TRIPLE-A", "roster_tripleA"),
            ("DOUBLE-A", "roster_doubleA"),
            ("SINGLE-A", "roster_singleA"),
            ("ON OPTION", "roster_tripleA_option"),
            ("ASSIGNED OUTRIGHT", "roster_outrighted"),
            ("FOREIGN", "roster_foreign"),
            ("RETIRED", "roster_retired"),
            ("NON-ROSTER", "roster_nonroster")
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

        for t in models.Team.objects.all():
            sheet = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t.tab_id}!A:V", value_cutoff=None)
            current_header = None
            players = []
            print(t)

            # Luxury cap only on team detail pages
            lux_cap_space = int(sheet[3][11].split('$')[1].strip().replace(',', ''))
            t.luxury_cap_space = lux_cap_space

            # Team founded only on team detail pages
            founded = int(sheet[0][10].split('f. ')[1].strip())
            t.initial_season = founded

            t.save()

            for row in sheet:
                if row == []:
                    continue
                if row == ['', 'FINANCIALS']:
                    current_header = None
                    break

                for header,x in ROSTER_HEADERS:
                    if header in row[1]:
                        current_header = header
                        
                if row[0] in ["-", "1"]:
                    player_dict = {
                        "roster_85man": False,
                        "roster_40man": False,
                        "roster_30man": False,
                        "roster_7dayIL": False,
                        "roster_56dayIL": False,
                        "roster_eosIL": False,
                        "roster_restricted": False,
                        "roster_tripleA": False,
                        "roster_tripleA_option": False,
                        "roster_outrighted": False,
                        "roster_foreign": False,
                        "roster_retired": False,
                        "roster_nonroster": False,
                        "roster_doubleA": False,
                        "roster_singleA": False,
                        "roster_owaivers": False,
                        "roster_r5waivers": False,
                        "recall_eligible": False,
                        "activation_eligible": False,
                        "waiver_clear": False,
                        "is_r5": False
                    }

                    if row[0] == "1":
                        player_dict['roster_40man'] = True
                        
                    for header, key in ROSTER_HEADERS:
                        if current_header == header:
                            player_dict[key] = True
                            if "aaa" in key:
                                player_dict['roster_tripleA'] = True

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