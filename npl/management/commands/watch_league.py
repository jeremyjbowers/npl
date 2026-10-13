"""Keep MLB debuts, club status, and this season's stats current.

The FanGraphs commands (``live_update``, ``live_download_fg_stats``) join on
FanGraphs ids. This command uses the MLB Stats API and MLBIDs.

Run it on a schedule, or leave ``--loop`` running:

    # every two hours; season stats load once after 6 AM Eastern
    python manage.py watch_league

    # long-running process: debuts and status every two hours, stats each morning
    python manage.py watch_league --loop
"""

import datetime
import time
from pathlib import Path

import pytz
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from npl import mlbwatch, utils

EASTERN = pytz.timezone("US/Eastern")


class Command(BaseCommand):
    help = "Check MLB debuts, club status, and IFA eligibility, and load this season's MLB stats by MLBID."

    def add_arguments(self, parser):
        parser.add_argument(
            "--appearances",
            action="store_true",
            help="Refresh debut and current club for the next batch of players.",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Load this season's major-league hitting and pitching.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="How many players to check for debut and club status (default 200).",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running. Status every --sleep seconds, season stats once each morning.",
        )
        parser.add_argument(
            "--sleep",
            type=int,
            default=60 * 60 * 2,
            help="Seconds between passes when --loop is set (default 2 hours).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["loop"]:
            self.stdout.write("Watching debuts, club status, and morning stats. Ctrl-C stops it.")
            while True:
                self._pass(options, scheduled=True)
                time.sleep(max(options["sleep"], 60))
            return
        explicit = options["appearances"] or options["stats"]
        self._pass(options, scheduled=not explicit)

    def _pass(self, options, scheduled):
        do_appearances = options["appearances"] or scheduled
        do_stats = options["stats"] or (scheduled and self._stats_due())
        if options["dry_run"]:
            self.stdout.write(
                f"Dry run. appearances={do_appearances} stats={do_stats} limit={options['limit']}"
            )
            return
        if do_appearances:
            players = mlbwatch.appearance_batch(options["limit"])
            count = mlbwatch.refresh_appearances(players)
            self.stdout.write(f"Checked {count} players against the MLB people endpoint.")
        if do_stats:
            season = utils.get_current_season()
            result = mlbwatch.load_season_stats(season)
            self._mark_stats_loaded()
            self.stdout.write(
                f"Loaded {season} stats for {result['hitting']} hitters and {result['pitching']} pitchers."
            )
        try:
            call_command("process_expired_auctions")
        except Exception as exc:
            self.stderr.write(f"Auction processing skipped: {exc}")

    def _state_path(self):
        return Path(settings.BASE_DIR) / "var" / "league_watch.json"

    def _stats_due(self):
        now = timezone.now().astimezone(EASTERN)
        if now.hour < 6:
            return False
        state = mlbwatch.read_state(self._state_path())
        return state.get("stats_on") != now.date().isoformat()

    def _mark_stats_loaded(self):
        today = datetime.datetime.now(EASTERN).date().isoformat()
        mlbwatch.write_state(self._state_path(), {"stats_on": today})
