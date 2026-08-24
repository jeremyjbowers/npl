from django.core.management.base import BaseCommand

from npl.models import Owner
from users.models import User
from users.names import domain_in_name_q, name_contains_domain


class Command(BaseCommand):
    help = (
        "Find users whose first or last name contains a domain (e.g. .com). "
        "Dry-run by default; pass --delete to remove them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete matching users. Without this flag, only list them.",
        )
        parser.add_argument(
            "--include-protected",
            action="store_true",
            help="Also consider staff, superusers, and league owners.",
        )

    def handle(self, *args, **options):
        delete = options["delete"]
        include_protected = options["include_protected"]

        users = User.objects.filter(domain_in_name_q()).order_by("id")
        if not include_protected:
            users = users.filter(is_staff=False, is_superuser=False)

        owner_user_ids = set(
            Owner.objects.exclude(user_id=None).values_list("user_id", flat=True)
        )

        matches = []
        skipped = []
        for user in users:
            if not (
                name_contains_domain(user.first_name)
                or name_contains_domain(user.last_name)
            ):
                continue
            if not include_protected and user.id in owner_user_ids:
                skipped.append(user)
                continue
            matches.append(user)

        if skipped:
            self.stdout.write(
                f"Skipping {len(skipped)} league owner(s) with domain-like names:"
            )
            for user in skipped:
                self.stdout.write(f"  skip {self._format_user(user)}")

        if not matches:
            self.stdout.write(self.style.SUCCESS("No spam users found."))
            return

        self.stdout.write(f"Found {len(matches)} user(s) with a domain in their name:")
        for user in matches:
            self.stdout.write(f"  {self._format_user(user)}")

        if not delete:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run. Re-run with --delete to remove these users."
                )
            )
            return

        deleted = 0
        for user in matches:
            user.delete()
            deleted += 1
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} user(s)."))

    def _format_user(self, user):
        return (
            f"id={user.id} email={user.email} "
            f"first_name={user.first_name!r} last_name={user.last_name!r}"
        )
