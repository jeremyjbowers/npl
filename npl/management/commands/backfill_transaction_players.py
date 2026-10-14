from django.core.management.base import BaseCommand
from django.db import transaction

from npl.transactions.players import apply_player_links


class Command(BaseCommand):
    help = (
        "Set the player on old ledger lines. An MLB id wins. Otherwise the "
        "name has to match one player, exactly or closely. Cash, picks, and "
        "other non-player lines are skipped. Lines that already have a player are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be linked, then leave the ledger unchanged.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            report = apply_player_links()
            self.stdout.write(
                f"Linked by MLB id: {report.mlb_id}. "
                f"Linked by name: {report.name}. "
                f"Linked by a close name: {report.fuzzy}. "
                f"Already linked: {report.already_linked}. "
                f"Non-player lines skipped: {report.skip}. "
                f"Ambiguous: {len(report.ambiguous)}. "
                f"Unmatched: {len(report.unmatched)}."
            )
            self._samples("Ambiguous names:", report.ambiguous)
            self._samples("Unmatched names:", [(label, ()) for label in report.unmatched])
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("Dry run: no rows were saved.")
                return
        self.stdout.write(self.style.SUCCESS("Player backfill finished."))

    def _samples(self, title, rows):
        if not rows:
            return
        self.stdout.write(title)
        for label, candidates in rows[:25]:
            extra = ""
            if candidates:
                extra = " — " + "; ".join(candidates)
            self.stdout.write(f"  {label}{extra}")
        remaining = len(rows) - 25
        if remaining > 0:
            self.stdout.write(f"  ... {remaining} more")
