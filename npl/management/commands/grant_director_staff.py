from django.core.management.base import BaseCommand

from npl.directors import grant_director_staff


class Command(BaseCommand):
    help = "Mark the league directors as staff and let them review transaction proposals."

    def handle(self, *args, **options):
        updated, missing = grant_director_staff()
        if updated:
            self.stdout.write(self.style.SUCCESS("Staff: " + ", ".join(updated)))
        else:
            self.stdout.write("No director accounts were updated.")
        if missing:
            self.stdout.write(self.style.WARNING("No login account yet for: " + ", ".join(missing)))
