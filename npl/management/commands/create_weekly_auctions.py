from django.core.management.base import BaseCommand
from django.utils import timezone
from npl.models import Auction, Player
import datetime
import pytz


class Command(BaseCommand):
    help = 'Create weekly auctions that expire on Fridays at 3 PM EST'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what auctions would be created without making changes',
        )
        parser.add_argument(
            '--max-players',
            type=int,
            default=10,
            help='Maximum number of players to put up for auction (default: 10)',
        )
        parser.add_argument(
            '--min-bid',
            type=int,
            default=1,
            help='Minimum bid amount for new auctions (default: $1)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_players = options['max_players']
        min_bid = options['min_bid']
        
        # Get current time in EST
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        
        # Calculate next Friday at 3 PM EST
        auction_close_time = self.get_next_friday_3pm(now)
        
        self.stdout.write(f'Creating auctions for next Friday: {auction_close_time}')
        
        # Check if we already have auctions for this week
        existing_auctions = Auction.objects.filter(
            closes=auction_close_time,
            active=True
        )
        
        if existing_auctions.exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Found {existing_auctions.count()} existing auctions for {auction_close_time}. Skipping creation.'
                )
            )
            return
        
        # Find eligible players for auction
        eligible_players = self.get_eligible_players(max_players)
        
        if not eligible_players:
            self.stdout.write(self.style.WARNING('No eligible players found for auction.'))
            return
        
        created_count = 0
        for player in eligible_players:
            if dry_run:
                self.stdout.write(f'  Would create auction for: {player.name} (min bid: ${min_bid})')
            else:
                auction = Auction.objects.create(
                    player=player,
                    closes=auction_close_time,
                    is_nomination=False,
                    min_bid=min_bid,
                    active=True
                )
                self.stdout.write(f'  ✓ Created auction for: {player.name} (ID: {auction.id})')
            created_count += 1
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'Would create {created_count} auctions.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created {created_count} auctions for {auction_close_time}.'))

    def get_next_friday_3pm(self, current_time):
        """Calculate the next Friday at 3 PM EST"""
        # Find next Friday
        days_until_friday = (4 - current_time.weekday()) % 7  # 4 = Friday (0=Monday)
        
        # If it's Friday and before 3 PM, use today. Otherwise, use next Friday.
        if days_until_friday == 0 and current_time.hour >= 15:  # After 3 PM on Friday
            days_until_friday = 7  # Next Friday
        elif days_until_friday == 0:  # Before 3 PM on Friday
            days_until_friday = 0  # Today
        
        next_friday = current_time + datetime.timedelta(days=days_until_friday)
        auction_close_time = next_friday.replace(hour=15, minute=0, second=0, microsecond=0)
        
        return auction_close_time

    def get_eligible_players(self, max_players):
        """
        Find players eligible for auction.
        Customize this logic based on your specific rules.
        """
        # Example criteria - modify as needed:
        eligible_players = Player.objects.filter(
            team__isnull=True,  # Unowned players
            is_owned=False,
            active=True,
            # Add more criteria as needed:
            # roster_status__in=['MINORS', 'MLB'],  # Only certain roster statuses
            # fg_is_mlb40man=False,  # Not on 40-man roster
        ).exclude(
            # Exclude players already in active auctions
            auction__active=True
        ).order_by('?')[:max_players]  # Random selection
        
        return eligible_players

    def add_nomination_auctions(self, current_time, dry_run):
        """
        Optional: Create nomination-only auctions for viewing purposes
        These don't accept bids but allow people to see who might be available
        """
        nomination_close_time = self.get_next_friday_3pm(current_time)
        
        # Get more players for nominations (non-binding)
        nomination_players = Player.objects.filter(
            team__isnull=True,
            is_owned=False,
            active=True,
        ).exclude(
            auction__active=True
        ).order_by('?')[:50]  # More players for nominations
        
        for player in nomination_players:
            if dry_run:
                self.stdout.write(f'  Would create nomination for: {player.name}')
            else:
                auction = Auction.objects.create(
                    player=player,
                    closes=nomination_close_time,
                    is_nomination=True,  # Nomination only
                    min_bid=1,
                    active=True
                )
                self.stdout.write(f'  ✓ Created nomination for: {player.name}') 