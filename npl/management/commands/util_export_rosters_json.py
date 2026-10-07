import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests

from npl import rosters


class Command(BaseCommand):
    help = (
        "Boil the NPL roster spreadsheet down to JSON. Downloads the sheet as "
        "xlsx (so cell colours / italics that encode contract type survive), "
        "parses every team tab, and writes data/rosters/npl_rosters.json."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Parse a local .xlsx export instead of downloading the sheet.",
        )
        parser.add_argument(
            "--out",
            default=os.path.join("data", "rosters", "npl_rosters.json"),
            help="Output path for the combined JSON (default: data/rosters/npl_rosters.json).",
        )
        parser.add_argument(
            "--per-team",
            action="store_true",
            help="Also write one file per team next to the combined output.",
        )
        parser.add_argument(
            "--tab",
            action="append",
            dest="tabs",
            help="Only parse this tab (repeatable), e.g. --tab 'Bulldog #18'.",
        )
        parser.add_argument(
            "--keep-xlsx",
            help="Save the downloaded workbook to this path for later --file runs.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            with open(options["file"], "rb") as f:
                source = f.read()
            self.stdout.write(f"Parsing {options['file']}")
        else:
            self.stdout.write(f"Downloading sheet {settings.ROSTER_SHEET_ID}")
            try:
                source = rosters.fetch_workbook(settings.ROSTER_SHEET_ID)
            except requests.HTTPError as e:
                raise CommandError(f"Sheet export failed: {e}")
            if options["keep_xlsx"]:
                with open(options["keep_xlsx"], "wb") as f:
                    f.write(source)

        parsed = rosters.parse_workbook(source, tabs=options["tabs"])

        out_path = options["out"]
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        n_players = sum(len(t["players"]) for t in parsed["teams"])
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(parsed['teams'])} teams / {n_players} players to {out_path}")
        )

        if options["per_team"]:
            base = os.path.dirname(out_path)
            for t in parsed["teams"]:
                slug = t["tab"].split("#")[0].strip().lower().replace(" ", "_")
                path = os.path.join(base, f"npl_{slug}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(t, f, indent=2, ensure_ascii=False)
                self.stdout.write(f"  {path}: {len(t['players'])} players")

        for w in parsed["warnings"]:
            self.stdout.write(self.style.WARNING(f"! {w}"))
