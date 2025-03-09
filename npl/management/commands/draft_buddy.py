
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import ujson as json
import requests
from nameparser import HumanName

from npl import models, utils

class Command(BaseCommand):
    drafted_path = "data/2025_r4_already_drafted.json"
    webhook_url = 'https://hooks.slack.com/services/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'
    message = ""
    already_drafted = {}
    new_draftees = {}
    
    def set_already_drafted(self):
        with open(self.drafted_path, 'r') as readfile:
            self.already_drafted = json.loads(readfile.read())

    def parse_new_draftees(self):
        players = utils.get_sheet(settings.LEAGUE_SHEET_ID, "2025 Rule 4!A:U", value_cutoff=None)
        for p in players:
            if p[0].strip() in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'CO']:
                team = p[4].strip()
                pick = p[3].strip()
                player = p[11].strip()
                mlb_id = p[13].strip()

                if len(mlb_id) >0:
                    if not self.already_drafted.get(mlb_id, None):
                        t_obj = models.Team.objects.get(full_name=team)
                        p_obj = models.Player.objects.get(mlb_id=mlb_id)
                        p_obj.team = t_obj
                        p_obj.save()
                        self.new_draftees[mlb_id] = f"With pick #{pick}, *{team}* takes *{player}* ({mlb_id})"

    def generate_message(self):
        for mlbid, message in self.new_draftees.items():
            self.message += f"{message}\n"

    def send_slack_message(self, webhook_url, message):
        r = requests.post(
            webhook_url, data=json.dumps({"text": message}),
            headers={'Content-Type': 'application/json'}
        )
        print(self.message)

    def post_message(self, quiet=False):

        if self.message.strip() != "":
            if not quiet:
                self.send_slack_message(self.webhook_url, self.message)

            for mlbid, message in self.new_draftees.items():
                self.already_drafted[mlbid] = message

            with open(self.drafted_path, 'w') as writefile:
                writefile.write(json.dumps(self.already_drafted))

    def handle(self, *args, **options):
        self.set_already_drafted()
        self.parse_new_draftees()
        self.generate_message()
        self.post_message(quiet=False)

