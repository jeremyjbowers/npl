from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

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
        }

        year_cols = ["2023","2024","2025","2026","2027","2028","2029","2030"]

        for t in models.Team.objects.all():
            team_players = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t.tab_id}!A:V", value_cutoff=None)
            team_players = [row for row in team_players if utils.is_player(row)]

            for p in team_players:
                player_obj = None
                if len(p) > 9:
                    contract_cells = p[9:]
                    contract_years = [{"year": v, "amount": utils.dollars_to_ints(k)} for k,v in list(zip(contract_cells, year_cols)) if k.strip() != ""]
                    if p[3].strip():
                        if p[3].strip() != "-":
                            player_obj = models.Player.objects.get(mlb_id=p[3].strip())

                    if not player_obj:

                        try:
                            player_obj = models.Player.objects.get(scoresheet_id=p[2].strip())

                        except models.Player.DoesNotExist:
                            if CROSSWALK.get(p[1].strip(), None):
                                player_obj = models.Player.objects.get(mlb_id=CROSSWALK.get(p[1].strip(), None))
                                
                    try:
                        c_obj = models.Contract.objects.get(team=t, player=player_obj)

                    except models.Contract.DoesNotExist:
                        c_obj = models.Contract(team=t, player=player_obj)

                    # create the contract
                    # add notes and buyouts etc
                    buyout = None
                    notes = None

                    try:
                        buyout = utils.dollars_to_ints(p[17])
                        c_obj.can_buyout = True
                        c_obj.buyout = buyout
                    except:
                        pass

                    if len(p) > 18:
                        notes = p[-1]
                        c_obj.notes = notes

                    c_obj.save()

                    # loop over years and add contract years as necessary
                    for cy in contract_years:
                        try:
                            cy_obj = models.ContractYear.objects.get(contract=c_obj, year=cy['year'])
                        except models.ContractYear.DoesNotExist:
                            cy_obj = models.ContractYear(contract=c_obj, year=cy['year'])

                        cy_obj.amount = cy['amount']
                        cy_obj.save()

                    c_obj.total_amount = sum([y['amount'] for y in contract_years])
                    c_obj.total_years = len(contract_years)
                    c_obj.save()
                    print(c_obj)