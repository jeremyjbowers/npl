import csv

from django.core.management.base import BaseCommand, CommandError

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        teams = {t.nickname: [] for t in models.Team.objects.all()}
        unowned = []
        unfound = []
        all_players = []

        players = utils.get_sheet("1Wb9f6QrGULjg2qs2Bmq6EWVXXKmw-WdYg-loYvGnpFY", f"DYNASTY_TOP!A:I")
        for p in players[1:]:
            p = dict(zip(players[0], p))
            print(p)
            obj = models.Player.objects.get(mlb_id=p['mlb_id'])
            if obj.team:
                p['npl'] = obj.team.nickname

                teams[obj.team.nickname].append({"name": p['player'], "rank": int(p['ba'])})

            else:
                unowned.append({"name": p['player'], "rank": int(p['ba'])})

            all_players.append(p)

        with open('all_players.csv', 'w') as writefile:
            fieldnames = all_players[0].keys()
            writer = csv.DictWriter(writefile, fieldnames=fieldnames)

            writer.writeheader()
            for p in all_players:
                writer.writerow(p)

        for team, players in teams.items():
            print(f"{team} ({len(players)})")
            top_50 = 0
            top_100 = 0
            top_250 = 0

            for p in players:
                if p['rank'] < 51:
                    top_50 += 1

                if p['rank'] < 101:
                    top_100 += 1

                if p['rank'] < 251:
                    top_250 += 1

            print(f"top 50: {top_50}  top 100: {top_100}  top 250: {top_250}")
            for p in players:
                print(f" {p['rank']} — {p['name']}")
            print("")

        print(f"UNFOUND ({len(unfound)})")
        for p in unfound:
            print(f" {p['rank']} — {p['name']}")
        print("")

        print(f"UNOWNED ({len(unowned)})")
        for p in unowned:
            print(f" {p['rank']} — {p['name']}")
        print("")