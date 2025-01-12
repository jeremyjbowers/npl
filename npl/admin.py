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
    TeamSeason,
    League,
    Division
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
    search_fields = ['player']
    list_display = ['player', 'closes', 'active']
    inlines = [MLBAuctionBidInline]
    autocomplete_fields = ['player']
    list_editable = ['active']


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


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    model = Team
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