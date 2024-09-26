from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from datetime import datetime

from npl import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        for auction in models.Auction.objects.filter(active=True):
            if auction.closes.date() < datetime.now():
                auction.active = False
                auction.save()