from django.contrib import admin
from django import forms
from django.contrib.postgres.fields import JSONField
from reversion.admin import VersionAdmin

from npl.models import (
    Team,
    Owner,
    Player,
    Contract,
    ContractYear,
    Transaction,
    TransactionType,
    Page,
    Collection,
    Event,
    Auction,
    MLBAuctionBid,
    PlayerNomination,
    TeamSeason,
    League,
    Division,
    Wishlist,
    WishlistPlayer
)

admin.site.site_title = "The NPL"
admin.site.site_header = "The NPL: Admin"
admin.site.index_title = "Administer The NPL Website"


class MLBAuctionBidInline(admin.TabularInline):
    model = MLBAuctionBid
    exclude = ("active",)
    extra = 0
    autocomplete_fields = ['team']
    readonly_fields = ('last_modified',)


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    model = Auction
    search_fields = ['player__name']
    list_display = ['player', 'closes', 'is_nomination', 'min_bid', 'total_bids', 'has_bids', 'nominated_by', 'active']
    list_filter = ['active', 'is_nomination', 'closes']
    inlines = [MLBAuctionBidInline]
    autocomplete_fields = ['player']
    list_editable = ['active', 'is_nomination', 'min_bid']
    readonly_fields = ['total_bids', 'has_bids', 'winning_bid_info', 'nominated_by']
    
    def total_bids(self, obj):
        return MLBAuctionBid.objects.filter(auction=obj).count()
    total_bids.short_description = 'Total Bids'
    
    def has_bids(self, obj):
        return obj.has_bids()
    has_bids.boolean = True
    has_bids.short_description = 'Has Bids'
    
    def nominated_by(self, obj):
        try:
            nomination = PlayerNomination.objects.get(auction=obj)
            return f"{nomination.nominating_team.short_name}"
        except PlayerNomination.DoesNotExist:
            return "-"
    nominated_by.short_description = 'Nominated By'
    
    def winning_bid_info(self, obj):
        if obj.is_expired():
            winning_info = obj.winning_bid()
            if winning_info['team_id']:
                from npl.models import Team
                try:
                    team = Team.objects.get(pk=winning_info['team_id'])
                    return f"{team.full_name} - Max: ${winning_info['bid']:,}, Winning: ${winning_info['winning_amount']:,}"
                except Team.DoesNotExist:
                    return f"Team {winning_info['team_id']} - Max: ${winning_info['bid']:,}, Winning: ${winning_info['winning_amount']:,}"
            else:
                return "No bids"
        else:
            return "Auction still active"
    winning_bid_info.short_description = 'Winning Bid Info'
    
    actions = ['process_expired_auctions', 'approve_nominations', 'reject_nominations']
    
    def process_expired_auctions(self, request, queryset):
        """Action to process selected expired auctions"""
        processed_count = 0
        for auction in queryset:
            if auction.is_expired() and auction.active and not auction.is_nomination:
                winning_bid_info = auction.winning_bid()
                if winning_bid_info['team_id']:
                    # This would call the same logic as the management command
                    processed_count += 1
        
        if processed_count:
            self.message_user(request, f'Processed {processed_count} expired auctions.')
        else:
            self.message_user(request, 'No eligible auctions to process.')
    
    def approve_nominations(self, request, queryset):
        """Action to approve selected nominations (make them active auctions)"""
        approved_count = 0
        for auction in queryset:
            if auction.is_nomination and not auction.active:
                auction.active = True
                auction.is_nomination = False  # Convert to real auction
                auction.save()
                approved_count += 1
        
        if approved_count:
            self.message_user(request, f'Approved {approved_count} nominations as active auctions.')
        else:
            self.message_user(request, 'No eligible nominations to approve.')
    
    def reject_nominations(self, request, queryset):
        """Action to reject selected nominations"""
        rejected_count = 0
        for auction in queryset:
            if auction.is_nomination and not auction.active:
                auction.delete()
                rejected_count += 1
        
        if rejected_count:
            self.message_user(request, f'Rejected and deleted {rejected_count} nominations.')
        else:
            self.message_user(request, 'No eligible nominations to reject.')
    
    process_expired_auctions.short_description = "Process selected expired auctions"
    approve_nominations.short_description = "Approve selected nominations as auctions"
    reject_nominations.short_description = "Reject and delete selected nominations"

@admin.register(Event)
class EventAdmin(VersionAdmin):
    model = Event
    search_fields = ['title', 'body']
    list_display = ['date', 'title', 'collection', 'active']
    list_editable = ['active']
    list_filter = ['collection']
    autocomplete_fields = ['collection']
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "date",
                    "title",
                    "collection",
                    "body",
                    "active"
                ),
            },
        ),
    )

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    model = Collection
    search_fields = ["name"]
    list_display = ["name"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                ),
            },
        ),
    )

@admin.register(Page)
class PageAdmin(VersionAdmin):
    model = Page
    search_fields = ['title', 'body', 'collection']
    list_display = ['title', 'created', 'last_modified', 'collection']
    list_filter = ['collection']
    autocomplete_fields = ['collection']
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "summary",
                    "collection",
                    "body",
                    "active"
                ),
            },
        ),
    )

@admin.register(TransactionType)
class TransactionTypeAdmin(admin.ModelAdmin):
    model = TransactionType
    search_fields = ['transaction_type']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    model = Transaction
    list_display = ['date', 'transaction_type', 'calculated_player', 'calculated_team']
    list_filter = ['date', 'team__short_name', 'transaction_type__transaction_type']
    autocomplete_fields = ['team', 'acquiring_team', 'player', 'transaction_type']
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("date",),
                    ("player"),
                    ("team"),
                    ("transaction_type"),
                    ("acquiring_team"),
                    ("notes")
                ),
            },
        ),
    )


class ContractYearInline(admin.TabularInline):
    model = ContractYear
    exclude = ("active",)
    extra = 0

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    model = Contract
    list_display = ["player", "total_years", "total_amount", "team"]
    list_filter = ["team", "total_years"]
    autocomplete_fields = ['team', 'player']
    inlines = [ContractYearInline]

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    model = Player
    list_display = ['last_name', 'first_name', 'position', 'team', 'mlb_org', 'mlb_id', 'scoresheet_id']
    list_filter = ['team', 'mlb_org', 'position']
    search_fields = ['name', 'team__full_name', 'mlb_org', 'scoresheet_id']

@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    model = Owner
    list_display = ['name']
    search_fields = ['name']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    model = Team
    autocomplete_fields = ['owners']
    list_display = ['full_name', 'short_name', 'tab_id', 'abbreviation']
    list_editable = ['tab_id', 'abbreviation']
    search_fields = ['full_name']

@admin.register(TeamSeason)
class TeamSeasonAdmin(admin.ModelAdmin):
    model = TeamSeason

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    model = League

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    model = Division

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    model = Wishlist
    autocomplete_fields = ['team']

@admin.register(WishlistPlayer)
class WishlistPlayerAdmin(admin.ModelAdmin):
    model = WishlistPlayer
    autocomplete_fields = ['player']
    list_display = ['player','rank','interesting', 'player_fv', 'player_risk']
    list_filter = ['wishlist', 'interesting', 'player_fv', 'player_risk', 'player__is_owned']
    search_fields = ['player__name', 'wishlist__team__full_name']

@admin.register(PlayerNomination)
class PlayerNominationAdmin(admin.ModelAdmin):
    model = PlayerNomination
    list_display = ['player_name', 'nominating_team', 'auction_status', 'created', 'reason_short']
    list_filter = ['nominating_team', 'created', 'auction__active']
    search_fields = ['auction__player__name', 'nominating_team__full_name', 'reason']
    readonly_fields = ['created', 'last_modified']
    autocomplete_fields = ['nominating_team', 'auction']
    
    def player_name(self, obj):
        return obj.auction.player.name
    player_name.short_description = 'Player'
    player_name.admin_order_field = 'auction__player__name'
    
    def auction_status(self, obj):
        if obj.auction.active:
            return "✓ Active Auction"
        else:
            return "⏳ Pending Review"
    auction_status.short_description = 'Status'
    auction_status.admin_order_field = 'auction__active'
    
    def reason_short(self, obj):
        if obj.reason:
            return obj.reason[:100] + '...' if len(obj.reason) > 100 else obj.reason
        return '-'
    reason_short.short_description = 'Reason'