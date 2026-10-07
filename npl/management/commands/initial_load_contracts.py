from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction

from npl import models, rosters


class Command(BaseCommand):
    help = (
        "Rebuild Contract / ContractYear from the roster spreadsheet. Reads the "
        "xlsx export via npl.rosters so each year carries its salary type "
        "(club/vesting/player option, pre-arb tier, arbitration) and whether "
        "the salary is covered by another team."
    )

    # Players on the sheet without an MLB id or scoresheet id, by raw name.
    CROSSWALK = {
        "Duno, Alfredo": "806957",
        "Valdez, Derniche": "806961",
        "Rodriguez, Jose": "800412",
        "Vargas, Marco": "804614",
        "Weiss, Zack": "592848",
        "Figuereo, Gleider": "699213",
        "Guerrero, Brailer": "806967",
        "Burrowes, Ryan": "802018",
        "Morales, Luis": "806960",
        "Guerrero, Pablo": "808326",
        "Francisca, Welbyn": "806988",
        "Cespedes, Yoelin": "806985",
        "Pegero, Antony": "803433",
        "Cepeda, Angel": "806980",
        "Lantigua, Arnaldo": "806984",
        "Espinoza, Ludwig": "806968",
        "Fleury, Jose": "800067",
        "Valdez, Luis": "692835",
        "De Los Santos, Anderson": "698945",
        "Pan, Wen-Hui": "808207",
        "Gonzalez, Cesar": "800177",
        "Mateo, Carlos": "801786",
        "Pachardo, Bladimir": "808097",
        "Di Turi, Filippo": "806995",
        "Antunez, Wuilfredo": "686404",
        "Liranzo, Joshua": "808162",
        "Monteverde, Carlos": "808272",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Parse a local .xlsx export instead of downloading the sheet.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report, but don't touch the database.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            with open(options["file"], "rb") as f:
                source = f.read()
        else:
            source = rosters.fetch_workbook(settings.ROSTER_SHEET_ID)

        parsed = rosters.parse_workbook(source)
        for w in parsed["warnings"]:
            self.stdout.write(self.style.WARNING(f"! {w}"))

        tabs_by_name = {t["tab"]: t for t in parsed["teams"]}
        tabs_by_number = {rosters.team_tab_number(t["tab"]): t for t in parsed["teams"]}

        created = 0
        missing = []

        with transaction.atomic():
            if not options["dry_run"]:
                models.Contract.objects.all().delete()

            for team in models.Team.objects.all():
                tab = self.find_tab(team, tabs_by_name, tabs_by_number)
                if tab is None:
                    self.stdout.write(self.style.WARNING(f"! no sheet tab for {team} (tab_id={team.tab_id!r})"))
                    continue

                for p in tab["players"]:
                    if not p["salaries"]:
                        continue
                    player_obj = self.find_player(p)
                    if player_obj is None:
                        missing.append(f"{tab['tab']}: {p['name']} ({p['mlb_id']})")
                        continue
                    if options["dry_run"]:
                        created += 1
                        continue
                    self.build_contract(team, player_obj, p)
                    created += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        for m in missing:
            self.stdout.write(self.style.WARNING(f"! no Player for {m}"))
        verb = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} contracts ({len(missing)} players not found)"))

    def find_tab(self, team, tabs_by_name, tabs_by_number):
        """Match a Team to its sheet tab by tab_id, falling back to the '#N' team number so renamed tabs still resolve."""
        tab = tabs_by_name.get(team.tab_id)
        if tab is None:
            tab = tabs_by_number.get(rosters.team_tab_number(team.tab_id))
            if tab is not None:
                self.stdout.write(f"  {team}: tab_id {team.tab_id!r} matched sheet tab {tab['tab']!r} by number")
        return tab

    def find_player(self, p):
        """Player.mlb_id is the PK (stored as a string)."""
        for mlb_id in (p["mlb_id"], self.CROSSWALK.get(p["name"])):
            if mlb_id:
                try:
                    return models.Player.objects.get(mlb_id=str(mlb_id))
                except models.Player.DoesNotExist:
                    pass
        if p["scoresheet_id"]:
            try:
                return models.Player.objects.get(scoresheet_id=str(p["scoresheet_id"]))
            except (models.Player.DoesNotExist, models.Player.MultipleObjectsReturned):
                pass
        return None

    def build_contract(self, team, player_obj, p):
        notes = [n for n in [p["contract_terms"], *p["notes"]] if n]
        c_obj = models.Contract(
            team=team,
            player=player_obj,
            notes="; ".join(notes) or None,
            can_buyout=p["buyout"] is not None,
            buyout=str(round(p["buyout"])) if p["buyout"] is not None else None,
            total_amount=round(sum(s["amount"] for s in p["salaries"])),
            total_years=len(p["salaries"]),
        )
        c_obj.save()
        models.ContractYear.objects.bulk_create(
            [
                models.ContractYear(
                    contract=c_obj,
                    year=s["year"],
                    amount=round(s["amount"]),
                    salary_type=s["type"],
                    is_covered=s["covered"],
                )
                for s in p["salaries"]
            ]
        )
        return c_obj
