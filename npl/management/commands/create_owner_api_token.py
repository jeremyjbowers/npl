from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from npl import models
from npl.api_tokens import TokenError, generate_token


class Command(BaseCommand):
    help = (
        "Create an owner API token for MCP access. "
        "Prints the token. The owner can also see it on /my/api-keys/."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Owner email or the linked user's email")
        parser.add_argument("--name", help="Owner name (icontains)")
        parser.add_argument(
            "--label",
            default="mcp",
            help="Label for this token, such as 'cursor laptop'. Default: mcp",
        )
        parser.add_argument(
            "--scope",
            choices=["read", "read_write"],
            default="read",
            help="read (lookups) or read_write (lookups and write actions). Default: read",
        )
        parser.add_argument("--list-owners", action="store_true", help="List owners and exit")

    def handle(self, *args, **options):
        if options["list_owners"]:
            owners = models.Owner.objects.select_related("user").order_by("name")
            for owner in owners:
                team = models.Team.objects.filter(owners=owner).first()
                abbr = team.abbreviation if team else "—"
                email = owner.email or (owner.user.email if owner.user_id else "")
                self.stdout.write(f"{owner.name}  <{email}>  team={abbr}")
            return

        email = options.get("email")
        name = options.get("name")
        if not email and not name:
            raise CommandError("Provide --email or --name (or --list-owners)")

        query = models.Owner.objects.select_related("user")
        if email:
            query = query.filter(Q(email__iexact=email) | Q(user__email__iexact=email))
        if name:
            query = query.filter(name__icontains=name)
        owners = list(query.distinct())
        if not owners:
            raise CommandError("No matching owner found")
        if len(owners) > 1:
            listing = ", ".join(f"{owner.name}<{owner.email}>" for owner in owners)
            raise CommandError(f"Ambiguous owner match: {listing}")

        owner = owners[0]
        if owner.user_id is None:
            raise CommandError(f"{owner.name} has no linked user, so they cannot hold an API key")
        try:
            token, raw = generate_token(owner.user, options["label"], options["scope"])
        except TokenError as exc:
            raise CommandError(str(exc)) from exc

        team = models.Team.objects.filter(owners=owner).first()
        self.stdout.write(self.style.SUCCESS("Created API token"))
        self.stdout.write(f"Owner: {owner.name} <{owner.email or owner.user.email}>")
        self.stdout.write(f"Team:  {team.abbreviation if team else 'none'}")
        self.stdout.write(f"Label: {token.name}")
        self.stdout.write(f"Scope: {token.get_scope_display()}")
        self.stdout.write("")
        self.stdout.write("Token (this owner can also see it on /my/api-keys/):")
        self.stdout.write(raw)
        self.stdout.write("")
        self.stdout.write("Preferred (HTTPS MCP):")
        self.stdout.write(
            '{\n'
            '  "mcpServers": {\n'
            '    "npl": {\n'
            '      "url": "https://YOUR-NPL-HOST/mcp",\n'
            '      "headers": {\n'
            f'        "Authorization": "Bearer {raw}"\n'
            '      }\n'
            '    }\n'
            '  }\n'
            '}'
        )
        self.stdout.write("")
        self.stdout.write("See documents/MCP.md for the stdio fallback and curl checks.")
