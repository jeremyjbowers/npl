from django.core.management.base import BaseCommand
from django.db import transaction

from npl.transactions.trades import persist_archive_trades


class Command(BaseCommand):
    help = (
        "Create a trade, with a UUID, for each old trade that is still only "
        "a run of ledger lines. Adjacent lines on the same date between the "
        "same two clubs become one trade. Lines that already have a trade are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created, then leave the ledger unchanged.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            summary = persist_archive_trades()
            self.stdout.write(
                f"Trades created: {summary['trades']}. "
                f"Ledger lines attached: {summary['receipts']}. "
                f"Already attached: {summary['already_linked']}. "
                f"Undated trade lines skipped: {summary['undated']}."
            )
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("Dry run: no rows were saved.")
                return
        self.stdout.write(self.style.SUCCESS("Trade backfill finished."))
