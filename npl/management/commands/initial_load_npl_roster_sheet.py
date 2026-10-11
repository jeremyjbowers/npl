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

                
            placed = self.place_players(t, players)
            touched.extend(placed)
            self.stdout.write(f"  {len(players)} players, saved {len(placed)}")
            self.stdout.flush()

        for player in models.Player.objects.filter(pk__in=touched, last_name=""):
            if not player.raw_name or ", " not in player.raw_name:
                continue
            player.first_name = player.raw_name.split(", ")[1].strip()
            player.last_name = player.raw_name.split(", ")[0].strip()
            player.save()

        self.stdout.write(self.style.SUCCESS(f"Placed {len(touched)} players onto {len(list(teams))} clubs."))

    def place_players(self, team, players):
        by_id = {}
        for payload in players:
            mlb_id = str(payload.get("mlb_id") or "").strip()
            if not mlb_id.isdigit():
                continue
            if payload.get("scoresheet_id") not in (None, ""):
                payload["scoresheet_id"] = str(payload["scoresheet_id"])
            if payload.get("mls_time") not in (None, ""):
                payload["mls_time"] = str(payload["mls_time"])
            if payload.get("mls_year") not in (None, ""):
                payload["mls_year"] = str(payload["mls_year"])
            by_id[mlb_id] = payload
        if not by_id:
            return []

        update_fields = [
            "team", "raw_name", "first_name", "last_name", "name",
            "scoresheet_id", "position", "simple_position", "mlb_org",
            "mls_time", "mls_year", "options", "status", "is_owned", "player_level",
            "roster_85man", "roster_40man", "roster_30man",
            "roster_7dayIL", "roster_56dayIL", "roster_eosIL",
            "roster_restricted", "roster_tripleA", "roster_tripleA_option",
            "roster_outrighted", "roster_foreign", "roster_retired",
            "roster_nonroster", "roster_doubleA", "roster_singleA",
            "roster_owaivers", "roster_r5waivers",
            "recall_eligible", "activation_eligible", "waiver_clear", "is_r5",
        ]
        fields = set(update_fields)
        existing = {
            player.mlb_id: player
            for player in models.Player.objects.filter(mlb_id__in=by_id).defer(
                "stats", "scoresheet_defense", "scoresheet_offense"
            )
        }
        to_create = []
        to_update = []
        for mlb_id, payload in by_id.items():
            player = existing.get(mlb_id)
            created = player is None
            if created:
                player = models.Player(mlb_id=mlb_id)
            for key, value in payload.items():
                if key in fields and key != "mlb_id":
                    setattr(player, key, value)
            player.team = team
            if player.options is None:
                player.options = 3
            player.set_name()
            player.set_owned()
            player.set_simple_position()
            player.set_options()
            player.player_level = player.set_player_level()
            if created:
                to_create.append(player)
            else:
                to_update.append(player)
        if to_create:
            models.Player.objects.bulk_create(to_create, batch_size=200)
        if to_update:
            models.Player.objects.bulk_update(to_update, update_fields, batch_size=200)
        return [player.mlb_id for player in to_create + to_update]