from django.core.management.base import BaseCommand
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            action="append",
            dest="only",
            help="Load one club, by full name or tab id. Repeat for more than one. Leaves every other club in place.",
        )

    def handle(self, *args, **options):
        teams = models.Team.objects.all().order_by("full_name")
        if options.get("only"):
            wanted = {name.strip().lower() for name in options["only"]}
            teams = [
                team for team in teams
                if team.full_name.lower() in wanted or (team.tab_id or "").lower() in wanted
            ]
            models.Player.objects.filter(team__in=teams).update(team=None)
        else:
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
        touched = []

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

        for t in teams:
            if not t.tab_id:
                self.stdout.write(f"No tab for {t.full_name}")
                continue
            sheet = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t.tab_id}!A:V", value_cutoff=None) or []
            current_header = None
            players = []
            self.stdout.write(t.full_name)
            self.stdout.flush()

            try:
                lux_cap_space = int(sheet[3][11].split('$')[1].strip().replace(',', ''))
                t.luxury_cap_space = lux_cap_space
                founded = int(sheet[0][10].split('f. ')[1].strip())
                t.initial_season = founded
                t.save()
            except (IndexError, ValueError, AttributeError):
                self.stdout.write(f"  could not read founded year or luxury cap for {t.full_name}")

            for row in sheet:
                if not row:
                    continue
                if len(row) < 2:
                    continue

                if row[0] == '' and row[1] == 'FINANCIALS':
                    current_header = None
                    break
                for header, x in ROSTER_HEADERS:
                    if header in row[1]:
                        current_header = header

                if row[0].strip() in ["-", "1", ""]:
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
                        
                    mlb_id = row[3].strip() if len(row) > 3 else ""
                    if len(row) < 7 or not mlb_id.isdigit():
                        continue
                    for header, key in ROSTER_HEADERS:
                        if current_header == header:
                            player_dict[key] = True
                            if "aaa" in key:
                                player_dict['roster_tripleA'] = True
                    if "," in row[1]:
                        players.append(utils.format_player_row(row, t, player_dict))

                
            self.stdout.write(f"  {len(players)} players")
            self.stdout.flush()
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
                        touched.append(player_obj.pk)

                except models.Player.DoesNotExist:
                    pass
                except Exception as exc:
                    self.stdout.write(f"  could not update {p.get('raw_name')}: {exc}")
                    player_obj = None

                if not player_obj:
                    if not p.get("mlb_id"):
                        continue
                    p["mlb_id"] = str(p["mlb_id"])
                    try:
                        player_obj = models.Player(**p)
                        player_obj.save()
                    except Exception as exc:
                        self.stdout.write(f"  could not save {p.get('raw_name')}: {exc}")
                        continue
                    touched.append(player_obj.pk)
                    self.stdout.write(f"+ {player_obj}")

        for player in models.Player.objects.filter(pk__in=touched, last_name=""):
            if not player.raw_name or ", " not in player.raw_name:
                continue
            player.first_name = player.raw_name.split(", ")[1].strip()
            player.last_name = player.raw_name.split(", ")[0].strip()
            player.save()

        self.stdout.write(self.style.SUCCESS(f"Placed {len(touched)} players onto {len(teams)} clubs."))