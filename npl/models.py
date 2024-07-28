import datetime
import os

from dateutil.relativedelta import *
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db.models.signals import post_save, m2m_changed
from django.utils.text import slugify
from django.dispatch import receiver
from django.conf import settings
from nameparser import HumanName
from django_quill.fields import QuillField
import pytz
import requests

from decimal import *

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
    simple_position = models.CharField(max_length=255, blank=True, null=True)
    birthdate = models.DateField(blank=True, null=True)
    birthdate_qa = models.BooleanField(default=False)
    mlb_org = models.CharField(max_length=255, blank=True, null=True)
    raw_age = models.IntegerField(default=None, blank=True, null=True)
    bats = models.CharField(max_length=3, blank=True, null=True)
    throws = models.CharField(max_length=3, blank=True, null=True)
    height = models.CharField(max_length=15, blank=True, null=True)
    weight = models.CharField(max_length=3, blank=True, null=True)
    last_verified = models.IntegerField(default=0)

    # Various MLB statuses
    roster_status = models.CharField(max_length=255, blank=True, null=True)
    fg_is_mlb40man = models.BooleanField(default=False)
    fg_is_injured = models.BooleanField(default=False)
    fg_is_starter = models.BooleanField(default=False)
    fg_is_bench = models.BooleanField(default=False)
    fg_injury_description = models.CharField(max_length=255, blank=True, null=True)
    fg_role = models.CharField(max_length=255, blank=True, null=True)
    fg_role_type = models.CharField(max_length=255, blank=True, null=True)


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

    # NPL roster status
    is_mlb_eligible = models.BooleanField(default=False)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    is_owned = models.BooleanField(default=False)
    is_roster_40_man = models.BooleanField(default=False)
    is_roster_30_man = models.BooleanField(default=False)
    is_roster_7_day_il = models.BooleanField(default=False)
    is_roster_56_day_il = models.BooleanField(default=False)
    is_roster_covid_il = models.BooleanField(default=False)
    is_roster_eos_il = models.BooleanField(default=False)
    is_roster_restricted = models.BooleanField(default=False)
    is_roster_aaa = models.BooleanField(default=False)
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
            return f"{self.position} {self.name} {self.mlb_org} ({self.team.nickname})"
        return f"{self.position} {self.name} {self.mlb_org}"


    @property
    def is_sp(self):
        return False
        # starter = False
        # mlb_checked = False
        # all_games = 0
        # started_games = 0
        # if self.simple_position:
        #     if "P" in self.simple_position:
        #         if self.pit_stats:
        #             for stat in self.pit_stats:
        #                 gs = stat.get('gamesStarted', 0)
        #                 g = stat.get('gamesPitched', 0)

        #                 if stat.get('level', '') == "MLB":
        #                     mlb_checked = True
        #                     if gs > 0 and g > 0:
        #                         if (gs / g) > 0.3: 
        #                             starter = True
        #                         else:
        #                             starter = False
        #                 else:
        #                     all_games += g
        #                     started_games += gs

        #             if started_games > 0 and all_games > 0:
        #                 if (started_games / all_games) > 0.3:
        #                     if not mlb_checked:
        #                         starter = True
        # return starter

    @property
    def level(self):
        if self.team:
            if self.is_roster_40_man:
                return "MLB"

            if self.mls_year:
                try:
                    if datetime.datetime.now().year - 1 < int(self.mls_year) < datetime.datetime.now().year + 2:
                        return "AA"
                    if int(self.mls_year) >= datetime.datetime.now().year + 2:
                        return "A"
                except:
                    pass
            return "AAA"
        return None


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
    def mlb_api_url(self):
        if self.mlb_id:
            return f"https://statsapi.mlb.com/api/v1/people/{self.mlb_id }"
        return None

    @property
    def fg_url(self):
        if self.fg_id:
            return f"https://www.fangraphs.com/statss.aspx?playerid={self.fg_id}"
        return None

    @property
    def contract(self):
        try:
            return Contract.objects.get(player=self, team=self.team)
        except Contract.DoesNotExist:
            pass
        return None

    def update_mlb_info(self):
        r = requests.get(self.mlb_api_url + "?hydrate=currentTeam,team")
        results = r.json().get('people', None)
        if results:
            if len(results) == 1:
                person = results[0]
                self.active = utils.to_bool(person['active'])

                if self.active:
                    self.first_name = person['firstName']
                    self.last_name = person['lastName']
                    self.birthdate = person['birthDate']

                    self.position = person['primaryPosition']['abbreviation']

                    try:
                        self.mlb_org = person['currentTeam']['abbreviation']
                    except KeyError:
                        pass
        
                    self.height = person['height']
                    self.weight = person['weight']
                    self.bats = person['batSide']['code']

                    try:
                        self.throws = person['pitchHand']['code']
                    except KeyError:
                        print(person)


    def set_simple_position(self):
        if self.position:
            if self.position.upper() in ["P", "SP", "RP", "LHP", "RHP", "SR"]:
                self.simple_position = "P"

            if self.position.upper() in ["IF", "1B", "2B", "3B", "SS"]:
                self.simple_position = "IF"

            if self.position.upper() in ["OF", "CF", "LF", "RF"]:
                self.simple_position = "OF"

            if "/" in self.position:
                self.simple_position = "UT"

            if self.position.upper() in ["C", "CA"]:
                self.simple_position = "C"

            if self.position.upper() == "UT":
                self.simple_position = "UT"

    def set_owned(self):
        if self.team == None:
            self.is_owned = False
        else:
            self.is_owned = True

    def set_name(self):
        if not self.name and not self.first_name and not self.last_name:
            if self.raw_name:
                self.name = self.raw_name

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
        self.set_simple_position()

        super().save(*args, **kwargs)

    def set_stats(self, stats_dict):
        if not self.stats:
            self.stats = {}

        if type(self.stats) is not dict:
            self.stats = {}

        self.stats[stats_dict["slug"]] = stats_dict

    def pit_stats(self):
        # should return stats dict by level and year
        payload = []
        has_mlb = False
        weak_mlb = False

        if self.stats:
            for year_side_level, stats in self.stats.items():
                if stats['side'] == "pitch":
                    payload.append(stats)

        payload = sorted(payload, key=lambda x:int(x['year']))

        return payload

    def hit_stats(self):
        # shoudl return stats dict by level and year
        payload = []
        has_mlb = False
        weak_mlb = False

        if self.stats:
            for year_side_level, stats in self.stats.items():
                if stats['side'] == "hit":
                    payload.append(stats)

        payload = sorted(payload, key=lambda x:int(x['year']))

        return payload


class TransactionType(BaseModel):
    transaction_type = models.CharField(max_length=255)


    class Meta():
        ordering = ['transaction_type']

    def __unicode__(self):
        return self.transaction_type


class Transaction(BaseModel):
    raw_date = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)

    raw_player = models.CharField(max_length=255, blank=True, null=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, blank=True, null=True)
    mlb_id = models.CharField(max_length=255, blank=True, null=True)

    cash_considerations = models.IntegerField(blank=True, null=True)

    raw_draft_pick = models.CharField(max_length=255, blank=True, null=True)
    # draft_pick = models.ForeignKey(DraftPick, on_delete=models.CASCADE)

    raw_team = models.CharField(max_length=255, blank=True, null=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team", null=True)

    raw_acquiring_team = models.CharField(max_length=255, blank=True, null=True)
    acquiring_team = models.ForeignKey(Team, on_delete=models.CASCADE, blank=True, null=True, related_name="acquiring_team")

    raw_transaction_type = models.CharField(max_length=255, blank=True, null=True)
    transaction_type = models.ForeignKey(TransactionType, on_delete=models.CASCADE, null=True)

    is_archive_transaction = models.BooleanField(default=False)

    notes = models.TextField(null=True, blank=True)

    class Meta():
        ordering = ['-date', 'transaction_type__transaction_type']


    def __unicode__(self):
        if self.acquiring_team:
            return f"{self.date}: {self.team} * {self.transaction_type} * {self.player} to {self.acquiring_team}"
        return f"{self.date}: {self.team} * {self.transaction_type} * {self.player}"

    @property
    def calculated_player(self):
        if self.player:
            return self.player
        try:
            if self.raw_player.strip() == "-":
                return None
        except:
            pass
        return self.raw_player

    @property
    def calculated_team(self):
        if self.team:
            return self.team.nickname
        try:
            if self.raw_team.strip() == "-":
                return None
        except:
            pass
        return self.raw_team

    @property
    def calculated_acquiring_team(self):
        if self.acquiring_team:
            return self.acquiring_team.nickname
        try:
            if self.raw_acquiring_team.strip() == "-":
                return None
        except:
            pass
        return self.raw_acquiring_team

    def set_player(self):
        if self.mlb_id and not self.player:
            self.player = Player.objects.get(mlb_id=self.mlb_id)

    def set_team(self):
        if self.raw_team and not self.team:
            team = self.raw_team
            if self.raw_team == "Hyperjets":
                team = "DockHounds"
            try:
                self.team = Team.objects.get(nickname__icontains=team)

            except Team.DoesNotExist:
                pass 

    def set_acquiring_team(self):
        if self.raw_acquiring_team and not self.acquiring_team:
            team = self.raw_acquiring_team
            if self.raw_team == "Hyperjets":
                team = "DockHounds"
            try:
                self.acquiring_team = Team.objects.get(nickname__icontains=team)

            except Team.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        if self.raw_date and not self.date:
            self.date = parser.parse(self.raw_date)

        self.set_team()
        self.set_acquiring_team()
        self.set_player()

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

    def years(self):
        base_years = 8
        contract_years = [p for p in ContractYear.objects.filter(contract=self)]
        extra_years = 8 - len(contract_years)
        for year in range(1, extra_years+1):
            contract_years.append({"amount": "-"})
        return contract_years


class ContractYear(BaseModel):
    year = models.IntegerField()
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.IntegerField()

    def __unicode__(self):
        return f"{self.year}: {self.contract.player.name}"

class Collection(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)

    class Meta:
        ordering = ["-name"]

    def __unicode__(self):
        return f"{self.name}"

    def slugify(self):
        self.slug = slugify(self.name)

    def save(self, *args, **kwargs):
        self.slugify()

        super().save(*args, **kwargs)

    @property
    def pages(self):
        return Page.objects.filter(collection=self)

class Page(BaseModel):
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, blank=True, null=True)
    summary = QuillField(blank=True,null=True)
    body = QuillField()

    class Meta:
        ordering = ["-title"]

    def __unicode__(self):
        return f"{self.title} — {self.last_modified}"

    def slugify(self):
        self.slug = slugify(self.title)

    def save(self, *args, **kwargs):
        self.slugify()

        super().save(*args, **kwargs)


class Event(BaseModel):
    date = models.DateField()
    title = models.CharField(max_length=255)
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, blank=True, null=True)
    body = QuillField(blank=True, null=True)

    class Meta:
        ordering = ['-date']

    def __unicode__(self):
        return f"{self.date}: {self.title}"


class Auction(BaseModel):
    player = models.ForeignKey(Player, null=True, on_delete=models.SET_NULL)
    closes = models.DateTimeField()

    class Meta:
        ordering = ['-closes']

    def time_left(self):
        now = datetime.datetime.now(pytz.timezone('US/Eastern'))
        if self.closes >= now:
            return self.closes - now
        return None

    def __unicode__(self):
        return f"{self.player.name} @ {self.closes}"


    def max_bid(self):
        bids = MLBAuctionBid.objects.filter(auction=self).order_by('-max_bid')
        if len(bids) > 0:
            return {"team_id": bids[0].team.pk,"bid": bids[0].max_bid}
        return {"team_id": None,"bid": 0}

    def leading_bid(self):
        bids = MLBAuctionBid.objects.filter(auction=self).order_by('-max_bid')
        if len(bids) > 0:
            if len(bids) == 1:
                return {"team_id": bids[0].team.pk,"bid": bids[0].max_bid}
            else:
                return {"team_id": bids[0].team.pk,"bid": bids[1].max_bid + 1}
        return {"team_id": None,"bid": 0}


class MLBAuctionBid(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE)
    max_bid = models.IntegerField()

    class Meta:
        unique_together = ['team', 'auction']

    def __unicode__(self):
        return f"{self.auction} > {self.team.nickname} ({self.max_bid})"