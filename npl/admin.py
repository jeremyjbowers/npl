from django.contrib import admin
from django import forms
from django.contrib.postgres.fields import JSONField

from npl.models import (
    Team,
    Owner,
    Player,
    Contract,
    ContractYear
)

admin.site.site_title = "The NPL"
admin.site.site_header = "The NPL: Admin"
admin.site.index_title = "Administer The NPL Website"

class ContractYearInline(admin.TabularInline):
    model = ContractYear
    exclude = ("active",)
    extra = 0

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    model = Contract
    list_display = ["player", "total_years", "total_amount", "team"]
    list_filter = ["team", "total_years"]
    inlines = [ContractYearInline]

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    model = Player
    list_display = ['last_name', 'first_name', 'position', 'team', 'mlb_org', 'is_roster_40_man']
    list_filter = ['team', 'mlb_org', 'is_roster_40_man', 'position']
    search_fields = ['name', 'team', 'mlb_org']

@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    model = Owner
    list_display = ['name']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    model = Team
    list_display = ["name", "division", "league"]
    list_filter = ["division", "league"]
    search_fields = ["name", "owner"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "nickname",
                    "division",
                    "league",
                    "owners",
                ),
            },
        ),
    )