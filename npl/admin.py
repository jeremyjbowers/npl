from django.contrib import admin
from django import forms
from django.contrib.postgres.fields import JSONField

from npl.models import (
    Team,
    Owner,
    Player,
    Contract,
    ContractYear,
    Transaction,
    TransactionType
)

admin.site.site_title = "The NPL"
admin.site.site_header = "The NPL: Admin"
admin.site.index_title = "Administer The NPL Website"

@admin.register(TransactionType)
class TransactionTypeAdmin(admin.ModelAdmin):
    model = TransactionType
    search_fields = ['transaction_type']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    model = Transaction
    list_display = ['date', 'transaction_type', 'calculated_player', 'calculated_team']
    list_filter = ['date', 'team__nickname', 'transaction_type__transaction_type']
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
    list_display = ['last_name', 'first_name', 'position', 'team', 'mlb_org', 'is_roster_40_man', 'mlb_id', 'scoresheet_id']
    list_filter = ['team', 'mlb_org', 'is_roster_40_man', 'position']
    list_editable = ['scoresheet_id']
    search_fields = ['name', 'team__name', 'mlb_org', 'scoresheet_id']
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "birthdate",
                    "raw_age",
                    ("position", 'simple_position'),
                    "mlb_id",
                    "scoresheet_id",
                    "mlb_org"
                ),
            },
        ),
    )

@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    model = Owner
    list_display = ['name']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    model = Team
    list_display = ["name", "division", "league"]
    list_filter = ["division", "league"]
    search_fields = ["name"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "nickname",
                    "division",
                    "league",
                    "tab_id",
                    "owners",
                ),
            },
        ),
    )