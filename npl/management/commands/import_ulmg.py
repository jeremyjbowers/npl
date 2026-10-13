"""Read roster status, level, and season stats from the ULMG database into NPL."""

from django.core.management.base import BaseCommand, CommandError

from npl.ulmg_import import database_url, fetch_rows, import_rows


class Command(BaseCommand):
    help = (
        "Copy roster status, affiliate level, and season stats from ULMG "
        "onto NPL players matched by MLB id or FanGraphs id."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many players would change without writing.",
        )
        parser.add_argument(
            "--years",
            nargs="*",
            type=int,
            help="Only copy these seasons. The current status line is the latest of this set.",
        )

    def handle(self, *args, **options):
        url = database_url()
        if not url:
            raise CommandError(
                "Set ULMG_DATABASE_URL to the ULMG Postgres connection string. "
                "The command reads that database, then writes only to NPL."
            )

        years = options.get("years") or None
        self.stdout.write("Reading ULMG player seasons...")
        rows = fetch_rows(url, years=years)
        summary = import_rows(rows, dry_run=options["dry_run"])

        verb = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(
            f"ULMG players read: {summary['ulmg_players']}\n"
            f"Matched to NPL: {summary['matched']}\n"
            f"Unmatched: {summary['skipped']}\n"
            f"Status rows: {summary['status']}\n"
            f"Stat lines: {summary['stat_lines']}\n"
            f"{verb}: {summary['updated']}"
        )
