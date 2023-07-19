import json

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests
from bs4 import BeautifulSoup

from npl import models, utils

class Command(BaseCommand):
    PIT_KEYS = ['p_game', 'p_total_pa', 'p_ab', 'p_total_hits', 'p_single', 'p_double', 'p_triple', 'p_home_run', 'p_strikeout', 'p_walk', 'p_earned_run', 'p_run', 'p_save', 'p_blown_save', 'p_out', 'p_win', 'p_loss', 'p_wild_pitch', 'p_balk', 'p_shutout', 'p_opp_batting_avg', 'p_opp_on_base_avg', 'p_total_stolen_base', 'p_pickoff_attempt_1b', 'p_pickoff_attempt_2b', 'p_pickoff_attempt_3b', 'p_pickoff_1b', 'p_pickoff_2b', 'p_pickoff_3b', 'p_lob', 'p_rbi', 'p_stolen_base_2b', 'p_stolen_base_3b', 'p_stolen_base_home', 'p_quality_start', 'p_walkoff', 'p_run_support', 'p_ab_scoring', 'p_automatic_ball', 'p_ball', 'p_called_strike', 'p_catcher_interf', 'p_caught_stealing_2b', 'p_caught_stealing_3b', 'p_caught_stealing_home', 'p_complete_game', 'p_defensive_indiff', 'p_foul', 'p_foul_tip', 'p_game_finished', 'p_game_in_relief', 'p_gnd_into_dp', 'p_gnd_into_tp', 'p_gnd_rule_double', 'p_hit_by_pitch', 'p_hit_fly', 'p_hit_ground', 'p_hit_line_drive', 'p_hit_into_play', 'p_hit_scoring', 'p_hold', 'p_intent_ball', 'p_intent_walk', 'p_missed_bunt', 'p_out_fly', 'p_out_ground', 'p_out_line_drive', 'p_passed_ball', 'p_pickoff_error_1b', 'p_pickoff_error_2b', 'p_pickoff_error_3b', 'p_pitchout', 'p_relief_no_out', 'p_sac_bunt', 'p_sac_fly', 'p_starting_p', 'p_swinging_strike', 'p_unearned_run', 'p_total_ball', 'p_total_bases', 'p_total_caught_stealing', 'p_total_pickoff', 'p_total_pickoff_attempt', 'p_total_pickoff_error', 'p_total_pitches', 'p_total_sacrifices', 'p_total_strike', 'p_total_swinging_strike', 'p_inh_runner', 'p_inh_runner_scored', 'p_beq_runner', 'p_beq_runner_scored', 'p_reached_on_error', 'p_formatted_ip', 'p_era', 'pitch_hand', 'n', 'n_ff_formatted', 'ff_avg_speed', 'ff_avg_spin', 'ff_avg_break_x', 'ff_avg_break_z', 'ff_avg_break', 'ff_range_speed', 'n_sl_formatted', 'sl_avg_speed', 'sl_avg_spin', 'sl_avg_break_x', 'sl_avg_break_z', 'sl_avg_break', 'sl_range_speed', 'n_ch_formatted', 'ch_avg_speed', 'ch_avg_spin', 'ch_avg_break_x', 'ch_avg_break_z', 'ch_avg_break', 'ch_range_speed', 'n_cukc_formatted', 'cu_avg_speed', 'cu_avg_spin', 'cu_avg_break_x', 'cu_avg_break_z', 'cu_avg_break', 'cu_range_speed', 'n_sift_formatted', 'si_avg_speed', 'si_avg_spin', 'si_avg_break_x', 'si_avg_break_z', 'si_avg_break', 'si_range_speed', 'n_fc_formatted', 'fc_avg_speed', 'fc_avg_spin', 'fc_avg_break_x', 'fc_avg_break_z', 'fc_avg_break', 'fc_range_speed', 'n_fs_formatted', 'fs_avg_speed', 'fs_avg_spin', 'fs_avg_break_x', 'fs_avg_break_z', 'fs_avg_break', 'fs_range_speed', 'n_kn_formatted', 'kn_avg_speed', 'kn_avg_spin', 'kn_avg_break_x', 'kn_avg_break_z', 'kn_avg_break', 'kn_range_speed', 'n_fastball_formatted', 'fastball_avg_speed', 'fastball_avg_spin', 'fastball_avg_break_x', 'fastball_avg_break_z', 'fastball_avg_break', 'fastball_range_speed', 'n_breaking_formatted', 'breaking_avg_speed', 'breaking_avg_spin', 'breaking_avg_break_x', 'breaking_avg_break_z', 'breaking_avg_break', 'breaking_range_speed', 'n_offspeed_formatted', 'offspeed_avg_speed', 'offspeed_avg_spin', 'offspeed_avg_break_x', 'offspeed_avg_break_z', 'offspeed_avg_break', 'offspeed_range_speed']
    HIT_KEYS = ['ab', 'pa', 'hit', 'single', 'double', 'triple', 'home_run', 'strikeout', 'walk', 'k_percent', 'bb_percent', 'batting_avg', 'slg_percent', 'on_base_percent', 'on_base_plus_slg', 'isolated_power', 'babip', 'xba', 'xslg', 'woba', 'xwoba', 'xobp', 'xiso', 'wobacon', 'xwobacon', 'bacon', 'xbacon', 'xbadiff', 'xslgdiff', 'wobadiff', 'exit_velocity_avg', 'launch_angle_avg', 'sweet_spot_percent', 'barrel', 'barrel_batted_rate', 'solidcontact_percent', 'flareburner_percent', 'poorlyunder_percent', 'poorlytopped_percent', 'poorlyweak_percent', 'hard_hit_percent', 'avg_best_speed', 'avg_hyper_speed', 'z_swing_percent', 'z_swing_miss_percent', 'oz_swing_percent', 'oz_swing_miss_percent', 'oz_contact_percent', 'out_zone_swing_miss', 'out_zone_swing', 'out_zone_percent', 'out_zone', 'meatball_swing_percent', 'meatball_percent', 'pitch_count_offspeed', 'pitch_count_fastball', 'pitch_count_breaking', 'pitch_count', 'iz_contact_percent', 'in_zone_swing_miss', 'in_zone_swing', 'in_zone_percent', 'in_zone', 'edge_percent', 'edge', 'whiff_percent', 'swing_percent', 'pull_percent', 'straightaway_percent', 'opposite_percent', 'batted_ball', 'f_strike_percent', 'groundballs_percent', 'groundballs', 'flyballs_percent', 'flyballs', 'linedrives_percent', 'linedrives', 'popups_percent', 'popups', 'b_total_pa', 'b_rbi', 'b_lob', 'b_total_bases', 'r_total_caught_stealing', 'r_total_stolen_base', 'b_ab_scoring', 'b_ball', 'b_called_strike', 'b_catcher_interf', 'b_foul', 'b_foul_tip', 'b_game', 'b_gnd_into_dp', 'b_gnd_into_tp', 'b_gnd_rule_double', 'b_hit_by_pitch', 'b_hit_ground', 'b_hit_fly', 'b_hit_into_play', 'b_hit_line_drive', 'b_hit_popup', 'b_out_fly', 'b_out_ground', 'b_out_line_drive', 'b_out_popup', 'b_intent_ball', 'b_intent_walk', 'b_interference', 'b_pinch_hit', 'b_pinch_run', 'b_pitchout', 'b_played_dh', 'b_sac_bunt', 'b_sac_fly', 'b_swinging_strike', 'r_caught_stealing_2b', 'r_caught_stealing_3b', 'r_caught_stealing_home', 'r_defensive_indiff', 'r_interference', 'r_pickoff_1b', 'r_pickoff_2b', 'r_pickoff_3b', 'r_run', 'r_stolen_base_2b', 'r_stolen_base_3b', 'r_stolen_base_home', 'b_total_ball', 'b_total_sacrifices', 'b_total_strike', 'b_total_swinging_strike', 'b_total_pitches', 'r_stolen_base_pct', 'r_total_pickoff', 'b_reached_on_error', 'b_walkoff', 'b_reached_on_int', 'pop_2b_sba_count', 'pop_2b_sba', 'pop_2b_sb', 'pop_2b_cs', 'pop_3b_sba_count', 'pop_3b_sba', 'pop_3b_sb', 'pop_3b_cs', 'exchange_2b_3b_sba', 'maxeff_arm_2b_3b_sba', 'n_outs_above_average', 'n_fieldout_5stars', 'n_opp_5stars', 'n_5star_percent', 'n_fieldout_4stars', 'n_opp_4stars', 'n_4star_percent', 'n_fieldout_3stars', 'n_opp_3stars', 'n_3star_percent', 'n_opp_2stars', 'n_2star_percent', 'n_fieldout_2stars', 'n_1star_percent', 'n_fieldout_1stars', 'n_opp_1stars', 'rel_league_reaction_distance', 'rel_league_burst_distance', 'rel_league_routing_distance', 'rel_league_bootup_distance', 'f_bootup_distance', 'n_bolts', 'hp_to_1b', 'sprint_speed']

    def nuke_stats(self):
        models.Player.objects.update(stats={})


    def get_mlb_pitching_stats(self):
        stats_url = "https://baseballsavant.mlb.com/leaderboard/custom?year=2023&type=pitcher&filter=&sort=1&sortDir=desc&min=1&selections=p_game,p_formatted_ip,k_percent,bb_percent,babip,p_era,p_starting_p,n,n_ff_formatted,ff_avg_speed,ff_avg_spin,ff_avg_break_x,ff_avg_break_z,ff_range_speed,n_sl_formatted,sl_avg_speed,sl_avg_spin,sl_avg_break_x,sl_avg_break_z,sl_range_speed,n_ch_formatted,ch_avg_speed,ch_avg_spin,ch_avg_break_x,ch_avg_break_z,ch_range_speed,n_cukc_formatted,cu_avg_speed,cu_avg_spin,cu_avg_break_x,cu_avg_break_z,cu_range_speed,n_sift_formatted,si_avg_speed,si_avg_spin,si_avg_break_x,si_avg_break_z,si_range_speed,n_fc_formatted,fc_avg_speed,fc_avg_spin,fc_avg_break_x,fc_avg_break_z,fc_range_speed,n_fs_formatted,fs_avg_speed,fs_avg_spin,fs_avg_break_x,fs_avg_break_z,fs_range_speed,&chart=false&x=p_game&y=p_game&r=no&chartType=beeswarm"
        r = requests.get(stats_url)

        soup = BeautifulSoup(r.content,'html.parser')

        script = soup.select('div.article-template script')[0].text.split('var data = ')[1].split(' var ')[0].strip().replace(';','')

        players = json.loads(script)

        for p in players:
            obj = models.Player.objects.get(mlb_id=p['player_id'])

            if not obj.stats:
                obj.stats = {'hitting': {}, "pitching": {}}

            for k,v in p.items():
                if k in self.PIT_KEYS:
                    obj.stats['pitching'][k] = v

            obj.save()
            print(f"* {obj}")

    def get_mlb_hitting_stats(self):
        stats_url = "https://baseballsavant.mlb.com/leaderboard/custom?year=2023&type=batter&filter=&sort=1&sortDir=desc&min=1&selections=player_age,pa,home_run,k_percent,bb_percent,batting_avg,slg_percent,on_base_percent,isolated_power,babip,r_total_caught_stealing,r_total_stolen_base,xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg,sweet_spot_percent,barrel_batted_rate,z_swing_percent,z_swing_miss_percent,oz_swing_percent,oz_swing_miss_percent,oz_contact_percent,out_zone_percent,meatball_swing_percent,meatball_percent,in_zone_percent,edge_percent,whiff_percent,swing_percent,&chart=false&x=xba&y=xba&r=no&chartType=beeswarm"
        r = requests.get(stats_url)

        soup = BeautifulSoup(r.content,'html.parser')

        script = soup.select('div.article-template script')[0].text.split('var data = ')[1].split(' var ')[0].strip().replace(';','')

        players = json.loads(script)

        for p in players:
            obj = models.Player.objects.get(mlb_id=p['player_id'])

            if not obj.stats:
                obj.stats = {'hitting': {}, "pitching": {}}

            for k,v in p.items():
                if k in self.HIT_KEYS:
                    obj.stats['hitting'][k] = v

            obj.save()
            print(f"* {obj}")

    def handle(self, *args, **options):
        self.nuke_stats()
        self.get_mlb_pitching_stats()
        self.get_mlb_hitting_stats()