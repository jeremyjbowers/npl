from django.core.cache import cache
from django.db.models import Count, Avg, Sum, Max, Min, Q
from . import models

def get_teams_with_stats():
    """
    Get all teams with related data and financial calculations cached for 5 minutes
    """
    cache_key = 'teams_with_financial_stats'
    teams = cache.get(cache_key)
    
    if teams is None:
        teams = models.Team.objects.select_related('division', 'league').prefetch_related('owners').all()
        
        # Calculate financial percentiles for all teams
        teams_list = list(teams)
        cap_spaces = [team.cap_space or 0 for team in teams_list]
        cash_amounts = [team.cash or 0 for team in teams_list]
        
        # Sort for percentile calculation
        cap_spaces_sorted = sorted(cap_spaces)
        cash_amounts_sorted = sorted(cash_amounts)
        
        for team in teams_list:
            # Calculate cap space percentile
            team_cap = team.cap_space or 0
            if cap_spaces_sorted:
                team.cap_space_percentile = (cap_spaces_sorted.index(team_cap) / len(cap_spaces_sorted)) * 100
            else:
                team.cap_space_percentile = 0
                
            # Calculate cash percentile  
            team_cash = team.cash or 0
            if cash_amounts_sorted:
                team.cash_percentile = (cash_amounts_sorted.index(team_cash) / len(cash_amounts_sorted)) * 100
            else:
                team.cash_percentile = 0
        
        cache.set(cache_key, teams_list, 300)  # Cache for 5 minutes
        teams = teams_list
    
    return teams

def get_player_search_results(filters):
    """
    Cache player search results based on filter parameters
    """
    # Create cache key from filter parameters
    cache_key = f"player_search_{hash(str(sorted(filters.items())))}"
    players = cache.get(cache_key)
    
    if players is None:
        # Build queryset based on filters
        queryset = models.Player.objects.select_related('team').all()
        
        if filters.get('name'):
            queryset = queryset.filter(name__icontains=filters['name'])
        if filters.get('team'):
            queryset = queryset.filter(team=filters['team'])
        if filters.get('position'):
            queryset = queryset.filter(simple_position=filters['position'])
        if filters.get('owned') is not None:
            queryset = queryset.filter(is_owned=filters['owned'])
            
        players = list(queryset[:500])  # Limit results
        cache.set(cache_key, players, 300)  # Cache for 5 minutes
    
    return players

def get_team_roster_stats(team_id):
    """
    Get cached roster statistics for a team
    """
    cache_key = f'team_roster_stats_{team_id}'
    stats = cache.get(cache_key)
    
    if stats is None:
        team_players = models.Player.objects.filter(team_id=team_id)
        
        stats = {
            'total_count': team_players.count(),
            'roster_40_man_count': team_players.filter(roster_40man=True).count(),
            'roster_30_man_count': team_players.filter(roster_30man=True).count(),
            'pitchers_count': team_players.filter(simple_position='P').count(),
            'hitters_count': team_players.exclude(simple_position='P').count(),
            'mlb_players_count': team_players.filter(roster_40man=True).count(),
            'minors_players_count': team_players.filter(roster_40man=False).count(),
        }
        
        cache.set(cache_key, stats, 300)  # Cache for 5 minutes
    
    return stats

def get_recent_transactions():
    """
    Get recent transactions cached
    """
    cache_key = 'recent_transactions'
    transactions = cache.get(cache_key)
    
    if transactions is None:
        transactions = list(
            models.Transaction.objects
            .select_related('player', 'team', 'acquiring_team', 'transaction_type')
            .order_by('-date', 'transaction_type')[:15]
        )
        cache.set(cache_key, transactions, 300)  # Cache for 5 minutes
    
    return transactions

def get_homepage_data():
    """
    Get all homepage data in one cached call
    """
    cache_key = 'homepage_data'
    data = cache.get(cache_key)
    
    if data is None:
        unowned_players = models.Player.objects.filter(team__isnull=True)
        
        data = {
            'total_count': unowned_players.count(),
            'pitchers': list(unowned_players.filter(simple_position="P").order_by('last_name')[:50]),
            'hitters': list(unowned_players.exclude(simple_position="P").order_by('simple_position', 'last_name')[:50]),
            'events': list(models.Event.objects.filter(active=True).order_by('date')[:8]),
            'transactions': get_recent_transactions(),
        }
        
        cache.set(cache_key, data, 300)  # Cache for 5 minutes
    
    return data

def invalidate_team_cache(team_id):
    """
    Invalidate team-related caches when team data changes
    """
    cache.delete(f'team_roster_stats_{team_id}')
    cache.delete('teams_with_financial_stats')
    cache.delete('homepage_teams_listing')
    cache.delete('teams_navigation_dropdown')

def invalidate_player_cache(player_id):
    """
    Invalidate player-related caches when player data changes
    """
    cache.delete('homepage_data')
    cache.delete('recent_transactions')
    # Clear search caches (this is broad but safe)
    cache.delete_pattern('player_search_*')

def invalidate_transaction_cache():
    """
    Invalidate transaction-related caches
    """
    cache.delete('recent_transactions')
    cache.delete('homepage_data') 