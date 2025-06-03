from django.core.management.base import BaseCommand
from django.utils import timezone
from npl.models import Auction, MLBAuctionBid, Transaction, TransactionType
import datetime
import pytz


class Command(BaseCommand):
    help = 'Process expired auctions and determine winners'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get current time in EST
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        
        # Find expired auctions that haven't been processed
        expired_auctions = Auction.objects.filter(
            closes__lt=now,
            active=True,
            is_nomination=False  # Only process actual auctions, not nominations
        )
        
        if not expired_auctions.exists():
            self.stdout.write(self.style.SUCCESS('No expired auctions to process.'))
            return
        
        self.stdout.write(f'Found {expired_auctions.count()} expired auctions to process.')
        
        for auction in expired_auctions:
            self.process_auction(auction, dry_run)
    
    def process_auction(self, auction, dry_run):
        """Process a single expired auction"""
        self.stdout.write(f'\nProcessing auction: {auction.player.name} (closed {auction.closes})')
        
        # Get all bids for this auction
        bids = MLBAuctionBid.objects.filter(auction=auction).order_by('-max_bid')
        
        if not bids.exists():
            self.stdout.write(f'  No bids found - auction ends with no winner')
            if not dry_run:
                auction.active = False
                auction.save()
            return
        
        # Determine winner and winning amount
        winning_bid_info = auction.winning_bid()
        winner_team_id = winning_bid_info['team_id']
        winning_amount = winning_bid_info['winning_amount']
        max_bid = winning_bid_info['bid']
        
        if winner_team_id:
            from npl.models import Team
            winner_team = Team.objects.get(pk=winner_team_id)
            
            self.stdout.write(f'  Winner: {winner_team.full_name}')
            self.stdout.write(f'  Max bid: ${max_bid:,}')
            self.stdout.write(f'  Winning amount: ${winning_amount:,}')
            
            if not dry_run:
                # Create transaction record for the winning bid
                try:
                    transaction_type = TransactionType.objects.get(transaction_type='Free Agent Auction')
                except TransactionType.DoesNotExist:
                    transaction_type, created = TransactionType.objects.get_or_create(
                        transaction_type='Free Agent Auction'
                    )
                
                # Create transaction
                from npl.models import Transaction
                transaction = Transaction.objects.create(
                    date=auction.closes.date(),
                    player=auction.player,
                    team=winner_team,
                    acquiring_team=winner_team,
                    transaction_type=transaction_type,
                    cash_considerations=winning_amount,
                    notes=f'Won auction with max bid of ${max_bid:,}, winning amount ${winning_amount:,}'
                )
                
                # Assign player to winning team
                auction.player.team = winner_team
                auction.player.is_owned = True
                auction.player.save()
                
                # Mark auction as processed
                auction.active = False
                auction.save()
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Transaction created and player assigned'))
        else:
            self.stdout.write(f'  No winner determined')
            if not dry_run:
                auction.active = False
                auction.save()
    
    def create_friday_auctions(self, dry_run):
        """
        Helper method to create weekly auctions that expire on Fridays at 3 PM EST
        This would typically be called by a separate command or cron job
        """
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        
        # Find next Friday at 3 PM EST
        days_until_friday = (4 - now.weekday()) % 7  # 4 = Friday
        if days_until_friday == 0 and now.hour >= 15:  # If it's Friday after 3 PM
            days_until_friday = 7  # Next Friday
        
        next_friday = now + datetime.timedelta(days=days_until_friday)
        auction_close_time = next_friday.replace(hour=15, minute=0, second=0, microsecond=0)
        
        self.stdout.write(f'Next auction close time: {auction_close_time}')
        
        # This is where you would create new auctions for free agents
        # Implementation depends on your specific business logic for which players to auction 