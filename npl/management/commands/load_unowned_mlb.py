import csv

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):

        """
        last_name,first_name,player_id,year,player_age,b_total_pa,xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg,barrel_batted_rate,
        """
        with open('data/2022_hitters.csv', 'r', encoding='utf-8-sig') as readfile:
            hitters = csv.DictReader(readfile)
                
            for h in hitters:
                
                try:
                    obj = models.Player.objects.get(mlb_id=h['player_id'])

                except models.Player.DoesNotExist:
                    obj = models.Player()
                    obj.mlb_id = h['player_id']

                obj.last_name = h['last_name']
                obj.first_name = h['first_name']
                obj.raw_age = h['player_age']
                obj.save()
                print(obj)

        """
        last_name,first_name,player_id,year,player_age,p_formatted_ip,xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg,barrel_batted_rate,
        """
        with open('data/2022_pitchers.csv', 'r', encoding='utf-8-sig') as readfile:
            pitchers = csv.DictReader(readfile)
                
            for h in pitchers:
                
                try:
                    obj = models.Player.objects.get(mlb_id=h['player_id'])

                except models.Player.DoesNotExist:
                    obj = models.Player()
                    obj.mlb_id = h['player_id']

                obj.last_name = h['last_name']
                obj.first_name = h['first_name']
                obj.raw_age = h['player_age']
                obj.position = "P"
                obj.save()
                print(obj)

        """
        last_name,first_name,player_id,display_team_name,year,primary_pos_formatted,fielding_runs_prevented,outs_above_average,outs_above_average_infront,outs_above_average_lateral_toward3bline,outs_above_average_lateral_toward1bline,outs_above_average_behind,outs_above_average_rhh,outs_above_average_lhh,actual_success_rate_formatted,adj_estimated_success_rate_formatted,diff_success_rate_formatted
        """
        with open('data/2022_fielding.csv', 'r', encoding='utf-8-sig') as readfile:
            pitchers = csv.DictReader(readfile)
                
            for h in pitchers:
                
                try:
                    obj = models.Player.objects.get(mlb_id=h['player_id'])

                except models.Player.DoesNotExist:
                    obj = models.Player()
                    obj.mlb_id = h['player_id']

                obj.last_name = h['last_name']
                obj.first_name = h['first_name']
                obj.position = h['primary_pos_formatted']
                obj.save()
                print(obj)