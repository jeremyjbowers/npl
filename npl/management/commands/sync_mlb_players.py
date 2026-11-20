"""Refresh player-level MLB fields, then add missing players who have an MLBID.

Updates every player already stored: name, height, weight, birth date,
position, bats, throws, birth country, debut, current MLB organization, and
whether he is on an MLB or minor-league roster. It does not touch the NPL
club, contract, roster flags, or stat lines.

Players on this season's MLB and affiliated minor-league lists who are not
in the database are inserted. The current club is read from the people
endpoint, because a season list can still name the team he was on earlier
in the year. Anyone already stored but absent from those lists is refreshed
the same way, which is how a released or retired player still gets a bio.

    python manage.py sync_mlb_players
    python manage.py sync_mlb_players --dry-run
    python manage.py sync_mlb_players --mlb-ids 592450,660271
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from npl.management.commands.load_mlb_rosters import fetch_teams, mlb_get
from npl.mlb_bios import AFFILIATED_SPORTS, index_teams, merge_people, sync_bios
from npl.mlbwatch import PEOPLE_CHUNK, _fetch_map


class Command(BaseCommand):
    help = (
        "Update non-stat MLB fields for every stored player, and import "
        "players on this season's MLB and minor-league lists who are missing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season the roster lists are read for. Defaults to LEAGUE_YEAR.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read MLB and report counts without writing.",
        )
        parser.add_argument(
            "--existing-only",
            action="store_true",
            help="Update players already stored and do not insert missing MLBIDs.",
        )
        parser.add_argument(
            "--mlb-ids",
            default="",
            help="Comma-separated MLBIDs. Limits the run to those players.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap how many players are written. Omit it for a full refresh.",
        )

    def handle(self, *args, **options):
        season = options["season"] or getattr(settings, "LEAGUE_YEAR", 2026)
        only_ids = [piece.strip() for piece in (options["mlb_ids"] or "").split(",") if piece.strip()]
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(f"Dry run for the {season} season. Nothing will be written.")

        levels, failed = self.fetch_season_players(season)
        mlb_list_ok = any(sport_id == 1 for sport_id, _people in levels)
        if not levels:
            self.stderr.write(
                "MLB returned no season lists (" + ", ".join(failed) + "). "
                "Stored players will be refreshed one id at a time."
            )
        elif failed:
            self.stdout.write("Levels MLB refused: " + ", ".join(failed))

        try:
            teams = index_teams(fetch_teams(season))
        except CommandError as exc:
            teams = {}
            self.stderr.write(str(exc))

        listed = merge_people(levels)
        self.stdout.write(f"{len(listed)} players with an MLBID on the {season} lists.")
        listed = self.use_current_teams(listed, only_ids or None)

        counts = sync_bios(
            listed,
            teams,
            self.fetch_people,
            mlb_list_ok=mlb_list_ok,
            create=not options["existing_only"],
            dry_run=dry_run,
            only_ids=only_ids or None,
            limit=options["limit"],
            log=self.stdout.write if options["verbosity"] >= 2 else None,
        )
        self.stdout.write(
            f"Updated {counts['updated']}, already current {counts['unchanged']}, "
            f"created {counts['created']}, skipped {counts['skipped']}."
        )
        if counts["not_found"] or counts["unresolved"]:
            self.stdout.write(
                f"MLB had no record for {counts['not_found']} id(s); "
                f"{counts['unresolved']} id(s) could not be read."
            )
        if (
            counts["updated"] == 0
            and counts["created"] == 0
            and counts["unchanged"] == 0
            and (failed or counts["unresolved"] or counts["not_found"])
        ):
            raise CommandError("MLB returned no player bios.")

    def fetch_season_players(self, season):
        levels = []
        failed = []
        for sport_id, label in AFFILIATED_SPORTS:
            response = mlb_get(
                f"https://statsapi.mlb.com/api/v1/sports/{sport_id}/players",
                params={"season": season},
            )
            if response is None or response.status_code != 200:
                status = getattr(response, "status_code", "no response")
                failed.append(f"{label} ({status})")
                self.stdout.write(f"Skipped {label}: {status}")
                continue
            try:
                people = response.json().get("people") or []
            except ValueError:
                failed.append(f"{label} (not JSON)")
                self.stdout.write(f"Skipped {label}: response was not JSON")
                continue
            self.stdout.write(f"{label}: {len(people)} players")
            levels.append((sport_id, people))
        return levels, failed

    def use_current_teams(self, listed, only_ids=None):
        """Replace list rows with the people payload, which has today's club.

        The season list is who held an MLBID. Its current team can still be
        the club a player was on earlier in the year. The people endpoint is
        the assignment MLB is publishing now. A player that endpoint does not
        return keeps the list row.
        """
        chosen = listed
        if only_ids:
            chosen = {mlb_id: listed[mlb_id] for mlb_id in only_ids if mlb_id in listed}
        if not chosen:
            return listed
        self.stdout.write(f"Reading current clubs for {len(chosen)} listed players.")
        found, _missing = self.fetch_people(list(chosen), label="listed players")
        updated = dict(listed)
        replaced = 0
        for mlb_id in chosen:
            person = found.get(str(mlb_id))
            if not person:
                continue
            updated[str(mlb_id)] = (person, None)
            replaced += 1
        self.stdout.write(f"Current club returned for {replaced} listed players.")
        return updated

    def fetch_people(self, mlb_ids, label="players not on a season list"):
        found = {}
        missing = set()

        def getter(url):
            response = mlb_get(url)
            if response is None or response.status_code != 200:
                status = getattr(response, "status_code", "no response")
                raise RuntimeError(f"{status} for {url}")
            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(f"people response was not JSON for {url}") from exc

        ids = [str(mlb_id) for mlb_id in mlb_ids if str(mlb_id).isdigit()]
        total = len(ids)
        for start in range(0, total, PEOPLE_CHUNK):
            chunk = ids[start : start + PEOPLE_CHUNK]
            got, gone = _fetch_map(chunk, "currentTeam", getter)
            found.update(got)
            missing.update(gone)
            done = min(start + PEOPLE_CHUNK, total)
            if done == total or done % 500 == 0:
                self.stdout.write(f"Read {done} of {total} {label}.")
        return found, missing
