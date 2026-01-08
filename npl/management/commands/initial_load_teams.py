import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


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
        if len(args) > 0:
            row = args[0]
            if len(row) > 0:
                if "AL: " not in row[0]:
                    if "NL: " not in row[0]:
                        return True
        return False

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


    def create_teams(self, *args, **options):
        teams = []

        teams = utils.get_sheet(settings.ROSTER_SHEET_ID, f"Key!A:H", value_cutoff=None)
        teams = [t for t in teams[38:] if self.is_team(t)]

        for t in teams:
            """
            ['Absolute Sickos', '', '69', '32', '32', '$41,901,354', '$11,455,475', '$6,600,000']
            """
            team_dict = {}
            team_dict['short_name'] = t[0].split()[-1].strip()
            team_dict['full_name'] = t[0].strip()
            team_dict['roster_85_man'] = int(t[2])
            team_dict['roster_40_man'] = int(t[3])
            team_dict['roster_30_man'] = int(t[4])
            team_dict['cap_space'] = int(t[5].replace(',', '').replace('$', ''))
            team_dict['cash'] = int(t[6].replace(',', '').replace('$', ''))
            team_dict['ifa'] = int(t[7].replace(',', '').replace('$', ''))

            ts_dict = {}
            ts_dict['roster_85_man'] = int(t[2])
            ts_dict['roster_40_man'] = int(t[3])
            ts_dict['roster_30_man'] = int(t[4])
            ts_dict['cap_space'] = int(t[5].replace(',', '').replace('$', ''))
            ts_dict['cash'] = int(t[6].replace(',', '').replace('$', ''))
            ts_dict['ifa'] = int(t[7].replace(',', '').replace('$', ''))


            print(team_dict)
            print(ts_dict)

            try:
                team_obj = models.Team.objects.get(short_name=team_dict['short_name'])
                for k,v in team_dict.items():
                    setattr(team_obj, k, v)

            except:
                team_obj = models.Team(**team_dict)

            try:
                ts_obj = models.TeamSeason.objects.get(team=team_obj, season=self.season)
                for k,v in ts_dict.items():
                    setattr(ts_obj, k, v)

            except:
                ts_obj = models.TeamSeason(**ts_dict)
                ts_obj.team = team_obj
                ts_obj.season = self.season

            team_obj.save()
            ts_obj.save()

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