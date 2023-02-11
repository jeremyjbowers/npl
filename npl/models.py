import datetime
import os

from dateutil.relativedelta import *
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from nameparser import HumanName

from npl import utils
from users.models import User

class BaseModel(models.Model):
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.__unicode__()


class Owner(BaseModel):
    name = models.CharField(max_length=255, null=True, blank=True)
    twitter = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=255, null=True, blank=True)
    hometown = models.CharField(max_length=255, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    first_year = models.IntegerField(null=True, blank=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE, blank=True, null=True)

    def __unicode__(self):
        return f"{self.name}"


class Team(BaseModel):
    name = models.CharField(max_length=255)
    nickname = models.CharField(max_length=255)
    league = models.CharField(max_length=255, null=True, blank=True)
    division = models.CharField(max_length=255, null=True, blank=True)
    championships = ArrayField(models.CharField(max_length=4), blank=True, null=True)
    playoffs = ArrayField(models.CharField(max_length=4), blank=True, null=True)
    tab_id = models.CharField(max_length=255, blank=True, null=True)
    owners = models.ManyToManyField(Owner, blank=True)

    # Financials
    cap_space = models.IntegerField(blank=True, null=True)
    reserves = models.IntegerField(blank=True, null=True)
    ifa_pool_space = models.IntegerField(blank=True, null=True)

    # Rosters
    roster_85_man = models.IntegerField(blank=True, null=True)
    roster_40_man = models.IntegerField(blank=True, null=True)
    roster_30_man = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ["nickname"]

    def __unicode__(self):
        return self.name

    def players(self):
        return Player.objects.filter(team=self)


class Player(BaseModel):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    name = models.CharField(max_length=255)
    raw_name = models.CharField(max_length=255, blank=True, null=True)
    position = models.CharField(max_length=255, blank=True, null=True)
    birthdate = models.DateField(blank=True, null=True)
    birthdate_qa = models.BooleanField(default=False)
    raw_age = models.IntegerField(default=None, blank=True, null=True)
    mlb_org = models.CharField(max_length=255, blank=True, null=True)

    scoresheet_defense = models.JSONField(null=True, blank=True)
    scoresheet_offense = models.JSONField(null=True, blank=True)

    # IDs
    mlb_id = models.CharField(max_length=255, primary_key=True)
    scoresheet_id = models.CharField(max_length=255, blank=True, null=True)
    fg_id = models.CharField(max_length=255, blank=True, null=True)
    bp_id = models.CharField(max_length=255, blank=True, null=True)
    bref_id = models.CharField(max_length=255, blank=True, null=True)

    # Contract status
    mls_time = models.CharField(max_length=255, blank=True, null=True)
    options = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    mls_year = models.CharField(max_length=255, blank=True, null=True)

    # Roster status
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    is_owned = models.BooleanField(default=False)
    is_roster_40_man = models.BooleanField(default=False)
    is_roster_30_man = models.BooleanField(default=False)
    is_roster_7_day_il = models.BooleanField(default=False)
    is_roster_56_day_il = models.BooleanField(default=False)
    is_roster_covid_il = models.BooleanField(default=False)
    is_roster_eos_il = models.BooleanField(default=False)
    is_roster_restricted = models.BooleanField(default=False)
    is_roster_aaa_option = models.BooleanField(default=False)
    is_roster_aaa_outright = models.BooleanField(default=False)
    is_roster_aaa_foreign = models.BooleanField(default=False)
    is_roster_aaa_retired = models.BooleanField(default=False)
    is_roster_aaa_nri = models.BooleanField(default=False)
    is_roster_aa = models.BooleanField(default=False)
    is_roster_a = models.BooleanField(default=False)

    # STATS
    # Here's the schema for a stats dictionary
    # required keys: year, level, type, timestamp
    # YEAR — the season these stats accrued in, or "career"
    # LEVEL - the levels these stats cover, e.g., A/AA or AA/AAA or MLB
    # TYPE — the type of stats, e.g., majors, minors
    # note: we combine all minor league stats in a single record
    # but we do not combine major leage WITH minor league.
    # this is because major league stats are used for the game
    # but minor / other pro league stats are not.
    # TIMESTAMP - a UNIX timestamp of when this record was created
    #
    # Any actual stats keys are fine following these.
    # Pitching and hitting stats can be in the same dictionary.
    #
    stats = models.JSONField(null=True, blank=True)

    class Meta():
        ordering = ['team__name', '-is_roster_40_man', 'position', 'last_name']

    def __unicode__(self):
        if self.team:
            return "%s (%s)" % (self.name, self.team.nickname)
        return self.name

    @property
    def mlb_image_url(self):
        return f"https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/{self.mlb_id}/headshot/67/current"

    @property
    def age(self):
        if self.birthdate:
            now = datetime.datetime.utcnow().date()
            return relativedelta(now, self.birthdate).years
        elif self.raw_age:
            return self.raw_age
        return None

    @property
    def mlb_url(self):
        if self.mlb_id:
            return f"https://www.mlb.com/player/{self.mlb_id}/"
        return None

    @property
    def fg_url(self):
        if self.fg_id:
            return f"https://www.fangraphs.com/statss.aspx?playerid={self.fg_id}"
        return None

    def set_owned(self):
        if self.team == None:
            self.is_owned = False
        else:
            self.is_owned = True

    def set_name(self):
        if self.first_name and self.last_name:
            name_string = "%s" % self.first_name
            name_string += " %s" % self.last_name
            self.name = name_string

        if self.name:
            if not self.first_name and not self.last_name:
                n = HumanName(self.name)
                self.first_name = n.first
                if n.middle:
                    self.first_name = n.first + " " + n.middle
                self.last_name = n.last
                if n.suffix:
                    self.last_name = n.last + " " + n.suffix


    def save(self, *args, **kwargs):
        self.set_name()
        self.set_owned()

        super().save(*args, **kwargs)


class Contract(BaseModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    total_amount = models.IntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    can_buyout = models.BooleanField(default=False)
    buyout = models.TextField(blank=True, null=True)
    total_years = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ['-total_years', '-total_amount']

    def __unicode__(self):
        return f"Contract: {self.player.name} to {self.team.nickname} — {self.total_years}y, ${self.total_amount}"


class ContractYear(BaseModel):
    year = models.IntegerField()
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.IntegerField()

    def __unicode__(self):
        return f"{self.year}: {self.contract.player.name}"