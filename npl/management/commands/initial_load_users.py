from django.core.management.base import BaseCommand
from django.conf import settings

from npl import models, utils
from npl.transactions.clubs import team_for_label
from users.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        rows = utils.get_sheet(settings.LEAGUE_SHEET_ID, "Team Owners!A:H", value_cutoff=None) or []
        header = 0
        for index, row in enumerate(rows):
            if row and row[0].strip().lower() == "team":
                header = index
                break

        current_team = ""
        attached = 0
        for row in rows[header + 1:]:
            if not row or not any(str(cell).strip() for cell in row):
                continue
            team_name = row[0].strip() if row[0].strip() else current_team
            if row[0].strip():
                current_team = team_name
            name = row[1].strip() if len(row) > 1 else ""
            if not name:
                continue

            year_joined = None
            if len(row) > 2 and row[2].strip().isdigit():
                year_joined = int(row[2].strip())
            email = row[3].strip() if len(row) > 3 else ""
            twitter = row[4].strip() if len(row) > 4 else ""
            phone = row[5].strip() if len(row) > 5 else ""
            hometown = row[6].strip() if len(row) > 6 else ""
            bio = row[7].strip() if len(row) > 7 else ""

            user = None
            if email:
                user = User.objects.filter(email__iexact=email).first()
                if user is None:
                    user = User(email=email)
                    user.set_unusable_password()
                    user.save()

            owner = models.Owner.objects.filter(name=name).first()
            if owner is None:
                owner = models.Owner(name=name)
            owner.year_joined = year_joined
            owner.email = email or owner.email
            owner.twitter = twitter or owner.twitter
            owner.phone = phone or owner.phone
            owner.hometown = hometown or owner.hometown
            owner.bio = bio or owner.bio
            if user:
                owner.user = user
            owner.save()

            team = models.Team.objects.filter(full_name__iexact=team_name).first() or team_for_label(team_name)
            if team is None:
                self.stdout.write(f"No club for {name} ({team_name})")
                continue
            team.owners.add(owner)
            attached += 1
            self.stdout.write(f"{owner.name} -> {team.full_name}")

        self.stdout.write(self.style.SUCCESS(f"Attached {attached} owners."))
