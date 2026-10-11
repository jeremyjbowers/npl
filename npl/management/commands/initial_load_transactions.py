import re
from collections import Counter

from dateutil.parser import parse
from django.conf import settings
from django.core.management.base import BaseCommand

from npl import models, utils
from npl.transactions.catalog import get_kind, normalize_sheet_type, sheet_asset_type
from npl.transactions.clubs import franchise_number

DEFAULT_YEARS = (2026, 2025)
SKIP_TYPES = {"", "transaction", "ss"}


def _cell(row, index):
    if index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _blank(value):
    return value.strip() in {"", "-", "—"}


def _mlb_id(value):
    text = value.strip()
    if _blank(text):
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


def _plain_dollars(notes):
    text = (notes or "").strip()
    if not text or not re.fullmatch(r"\$[\d,]+k?", text, flags=re.IGNORECASE):
        return None
    multiplier = 1000 if text.lower().endswith("k") else 1
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return int(digits) * multiplier


def parse_transaction_row(row):
    """Turn one sheet row into Transaction fields, or None when it is not a transaction."""
    raw_date = _cell(row, 0)
    raw_type = _cell(row, 5)
    if normalize_sheet_type(raw_type) is None and raw_type.strip().lower() in SKIP_TYPES:
        return None
    try:
        when = parse(raw_date).date()
    except (TypeError, ValueError, OverflowError):
        return None

    player = _cell(row, 2)
    notes = _cell(row, 7)
    acquiring = _cell(row, 6)
    payload = {
        "raw_date": raw_date,
        "date": when,
        "raw_team": _cell(row, 1),
        "raw_player": player,
        "mlb_id": _mlb_id(_cell(row, 4)),
        "raw_transaction_type": raw_type,
        "raw_acquiring_team": "" if _blank(acquiring) else acquiring,
        "notes": notes,
        "is_archive_transaction": True,
        "cash_considerations": None,
        "raw_draft_pick": "",
    }
    asset = sheet_asset_type(player)
    if asset in {"cash", "ifa", "cap"}:
        payload["cash_considerations"] = _plain_dollars(notes)
    if asset == "draft_pick":
        payload["raw_draft_pick"] = notes
    return payload


class Command(BaseCommand):
    help = "Load archived transactions from the 2026 and 2025 transaction sheets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            action="append",
            type=int,
            dest="years",
            help="Sheet year to load. Repeat for more than one. Default: 2026 and 2025.",
        )

    def handle(self, *args, **options):
        years = options["years"] or list(DEFAULT_YEARS)
        deleted, _ = models.Transaction.objects.filter(is_archive_transaction=True).delete()
        if deleted:
            self.stdout.write(f"Removed {deleted} previously archived transactions.")

        loaded = 0
        skipped = 0
        unmatched = Counter()
        unknown_types = Counter()
        for year in years:
            title = f"{year} Transactions"
            rows = utils.get_sheet(settings.LEAGUE_SHEET_ID, f"{title}!A:H", value_cutoff=None) or []
            year_loaded = 0
            for row in rows:
                payload = parse_transaction_row(row)
                if payload is None:
                    skipped += 1
                    continue
                code = normalize_sheet_type(payload["raw_transaction_type"])
                if code:
                    kind = get_kind(code)
                    transaction_type, _ = models.TransactionType.objects.get_or_create(
                        code=code,
                        defaults={
                            "transaction_type": kind["label"],
                            "category": kind["category"],
                            "requires_agreement": kind["requires_agreement"],
                            "requires_contract": kind["requires_contract"],
                        },
                    )
                else:
                    unknown_types[payload["raw_transaction_type"]] += 1
                    transaction_type, _ = models.TransactionType.objects.get_or_create(
                        transaction_type=payload["raw_transaction_type"]
                    )
                if payload["raw_team"] and franchise_number(payload["raw_team"]) is None:
                    unmatched[payload["raw_team"]] += 1
                if payload["raw_acquiring_team"] and franchise_number(payload["raw_acquiring_team"]) is None:
                    unmatched[payload["raw_acquiring_team"]] += 1
                transaction = models.Transaction(**payload)
                transaction.transaction_type = transaction_type
                transaction.save()
                year_loaded += 1
            loaded += year_loaded
            self.stdout.write(f"{title}: {year_loaded} transactions.")

        self.stdout.write(self.style.SUCCESS(f"Loaded {loaded} archived transactions."))
        if unknown_types:
            self.stdout.write("Unrecognized transaction labels:")
            for label, count in unknown_types.most_common():
                self.stdout.write(f"  {count:5} {label}")
        if unmatched:
            self.stdout.write("Club names that are not one of the 24 franchises:")
            for label, count in unmatched.most_common():
                self.stdout.write(f"  {count:5} {label}")
        else:
            self.stdout.write("Every club name matched a franchise number.")
