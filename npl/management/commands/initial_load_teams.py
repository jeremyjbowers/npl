import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils
from npl.transactions.clubs import franchise_number, tab_id_for


def _number(value):
    text = str(value or "").strip().replace(",", "").replace("$", "").replace(" ", "")
    if text in {"", "-"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


class Command(BaseCommand):
    season = None

    def is_important(self, *args, **options):
        if len(args) > 0:
            row = args[0]
            if self.is_division(row):
                return True
            if self.is_team(row):
                return True
        return False

    def is_team(self, *args, **options):
        if not args or not args[0] or not args[0][0].strip():
            return False
        row = args[0]
        if "AL:" in row[0] or "NL:" in row[0]:
            return False
        # Division headers and notes share this block. A club row has a roster count.
        return _number(row[2] if len(row) > 2 else "") is not None

    def is_division(self, *args, **options):
        if len(args) > 0:
            row = args[0]
            if len(row) > 0:
                if "AL:" in row[0]:
                    return True
                if "NL:" in row[0]:
                    return True
        return False

    def get_league_division(self, *args, **options):
        if len(args) > 0:
            row = args[0]
            if ":" in row[0]:
                name = row[0].split(':')[1].strip().lower().title()
                league = row[0].split(':')[0].strip()
                return (league, name)
        return None

    def get_team(self, *args, **options):
        if len(args) > 0:
            row = args[0]
            if not ":" in row[0]:
                return row[0].strip()

    def create_divisions(self, *args, **options):
        divisions = utils.get_sheet(settings.ROSTER_SHEET_ID, f'Key!A:H', value_cutoff=None)
        divisions = [d for d in divisions[38:] if self.is_division(d)]

        for division in divisions:
            league, division = self.get_league_division(division)
            league_obj = models.League.objects.get(name=league)
            division_obj, created = models.Division.objects.get_or_create(name=division, league=league_obj)


    def create_leagues(self, *args, **options):
        for league in ['AL', 'NL']:
            league_obj, created = models.League.objects.get_or_create(name=league)


    def create_season(self, *args, **options):
        season, created = models.Season.objects.get_or_create(year=settings.LEAGUE_YEAR)
        return season


    def create_teams(self, *args, **options):
        teams = []

        teams = utils.get_sheet(settings.ROSTER_SHEET_ID, f"Key!A:H", value_cutoff=None)
        teams = [t for t in teams[38:] if self.is_team(t)]

        for t in teams:
            """
            ['Absolute Sickos', '', '69', '32', '32', '$41,901,354', '$11,455,475', '$6,600,000']
            """
            full_name = t[0].strip()
            short_name = full_name.split()[-1].strip()
            counts = [_number(t[i] if len(t) > i else "") for i in range(2, 8)]
            if any(count is None for count in counts):
                continue
            roster_85, roster_40, roster_30, cap_space, cash, ifa = counts
            number = franchise_number(full_name)
            team_dict = {
                "short_name": short_name,
                "full_name": full_name,
                "cap_space": cap_space,
                "cash": cash,
                "ifa": ifa,
            }
            if number:
                team_dict["tab_id"] = tab_id_for(number)

            team_obj = models.Team.objects.filter(short_name=short_name).first()
            if team_obj is None and team_dict.get("tab_id"):
                team_obj = models.Team.objects.filter(tab_id=team_dict["tab_id"]).first()
            if team_obj is None:
                team_obj = models.Team(**team_dict)
            else:
                for key, value in team_dict.items():
                    setattr(team_obj, key, value)
            team_obj.save()

            ts_obj = models.TeamSeason.objects.filter(team=team_obj, season=self.season).first()
            if ts_obj is None:
                ts_obj = models.TeamSeason(team=team_obj, season=self.season)
            ts_obj.roster_85_man = roster_85
            ts_obj.roster_40_man = roster_40
            ts_obj.roster_30_man = roster_30
            ts_obj.cap_space = cap_space
            ts_obj.cash = cash
            ts_obj.ifa = ifa
            ts_obj.save()
            self.stdout.write(f"{team_obj.tab_id or short_name}: 40-man {roster_40}, cap {cap_space}")

    def assign_teams(self, *args, **options):
        all_rows = utils.get_sheet(settings.ROSTER_SHEET_ID, f'Key!A:H', value_cutoff=None)
        rows = [r for r in all_rows[38:] if self.is_important(r)]

        division = None
        league = None

        for row in rows:
            if self.get_league_division(row):
                league, division = self.get_league_division(row)
                
            if self.get_team(row):
                team = self.get_team(row)

                league_obj = models.League.objects.get(name=league)
                division_obj = models.Division.objects.get(name=division)
                team_obj = models.Team.objects.get(full_name=team)

                team_obj.league = league_obj
                team_obj.division = division_obj

                division_obj.league = league_obj

                team_obj.save()
                division_obj.save()

    def handle(self, *args, **options):
        self.season = self.create_season()
        self.create_leagues()
        self.create_divisions()
        self.create_teams()
        self.assign_teams()