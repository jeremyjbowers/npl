from django.core.management.base import BaseCommand
from django.db import transaction
from npl.models import Player


class Command(BaseCommand):
    help = 'Save all player objects to update computed fields like player_level'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        players = Player.objects.all()
        total_players = players.count()
        
        self.stdout.write(f'Found {total_players} players to process...')
        
        updated_count = 0
        
        with transaction.atomic():
            for i, player in enumerate(players, 1):
                old_level = player.player_level
                
                if not dry_run:
                    # Save the player, which will trigger set_player_level()
                    player.save()
                    player.refresh_from_db()
                
                new_level = player.player_level
                
                if old_level != new_level:
                    updated_count += 1
                    self.stdout.write(
                        f'Player {player.name} ({player.mlb_id}): {old_level} -> {new_level}'
                    )
                
                # Show progress every 100 players
                if i % 100 == 0:
                    self.stdout.write(f'Processed {i}/{total_players} players...')
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'DRY RUN: Would update {updated_count} players out of {total_players}'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated {updated_count} players out of {total_players}'
                )
            ) 