import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils
from npl.books import apply_key_sheet
from npl.sheetload import parse_key_sheet


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
        return season


    def create_teams(self, *args, **options):
        for row in self.key.get("teams") or []:
            full_name = row["full_name"]
            short_name = full_name.split()[-1].strip()
            team_obj = models.Team.objects.filter(full_name=full_name).first()
            if team_obj is None:
                team_obj = models.Team.objects.filter(short_name=short_name).first()
            if team_obj is None:
                team_obj = models.Team(full_name=full_name, short_name=short_name)
            else:
                team_obj.full_name = full_name
                team_obj.short_name = short_name
            for field in ("cap_space", "cash", "ifa"):
                if row.get(field) is not None:
                    setattr(team_obj, field, row[field])
            team_obj.save()

            team_season = models.TeamSeason.objects.filter(team=team_obj, season=self.season).first()
            if team_season is None:
                team_season = models.TeamSeason(team=team_obj, season=self.season)
            for field, source in (
                ("cap_space", "cap_space"),
                ("cash", "cash"),
                ("ifa", "ifa"),
                ("roster_85_man", "roster_85"),
                ("roster_40_man", "roster_40"),
                ("roster_30_man", "roster_30"),
            ):
                if row.get(source) is not None:
                    setattr(team_season, field, row[source])
            team_season.save()

    def assign_teams(self, *args, **options):
        all_rows = utils.get_sheet(settings.ROSTER_SHEET_ID, f'Key!A:H', value_cutoff=None) or []
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
        key = utils.get_sheet(settings.ROSTER_SHEET_ID, "Key!A:H", value_cutoff=None) or []
        self.key = parse_key_sheet(key)
        self.season = self.create_season()
        self.create_leagues()
        self.create_divisions()
        self.create_teams()
        self.assign_teams()
        apply_key_sheet(self.key)