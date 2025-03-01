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


class League(BaseModel):
    name = models.CharField(max_length=255, blank=True, null=True)

    def __unicode__(self):
        return self.name


class Division(BaseModel):
    name = models.CharField(max_length=255, blank=True, null=True)
    league = models.ForeignKey(League, on_delete=models.SET_NULL, blank=True, null=True)
    def __unicode__(self):
        return f"{self.league}: {self.name}"


class Season(BaseModel):
    year = models.IntegerField()
    year_start = models.DateField(null=True, blank=True)
    year_end = models.DateField(null=True, blank=True)
    term_pay_1 = models.DateField(null=True, blank=True)
    term_pay_2 = models.DateField(null=True, blank=True)
    opening_day	= models.DateField(null=True, blank=True)
    league_min = models.IntegerField(null=True, blank=True)
    qo_salary = models.IntegerField(null=True, blank=True)
    salary_cap = models.IntegerField(null=True, blank=True)

    def __unicode__(self):
        return f"The {self.year} NPL season"


class Owner(BaseModel):
    name = models.CharField(max_length=255, null=True, blank=True)
    twitter = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    hometown = models.CharField(max_length=255, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    year_joined = models.IntegerField(null=True, blank=True)
    year_left = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    discord = models.CharField(max_length=255, null=True, blank=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE, blank=True, null=True)

    def __unicode__(self):
        return f"{self.name}"


class Team(BaseModel):
    full_name = models.CharField(max_length=255, null=True)
    short_name = models.CharField(max_length=255, null=True)
    abbreviation = models.CharField(max_length=25, null=True)
    initial_season = models.IntegerField(blank=True, null=True)
    final_season = models.IntegerField(blank=True, null=True)
    owners = models.ManyToManyField(Owner, blank=True)

    # League + division / denormalized
    league = models.ForeignKey(League, on_delete=models.SET_NULL, blank=True, null=True)
    division = models.ForeignKey(Division, on_delete=models.SET_NULL, blank=True, null=True)
    tab_id = models.CharField(max_length=255, blank=True, null=True)

    # Farm system
    triple_a_name = models.CharField(max_length=255, blank=True, null=True)
    double_a_name = models.CharField(max_length=255, null=True, blank=True)
    single_a_name = models.CharField(max_length=255, null=True, blank=True)

    # Financials / denormalized
    contract_salary = models.IntegerField(blank=True, null=True)
    carried_salary = models.IntegerField(blank=True, null=True)
    cash_borrowing = models.IntegerField(blank=True, null=True)
    cap_space = models.IntegerField(blank=True, null=True)
    luxury_cap_space = models.IntegerField(blank=True, null=True)
    cash = models.IntegerField(blank=True, null=True)
    ifa = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ["full_name"]

    def __unicode__(self):
        return self.name

    def players(self):
        return Player.objects.filter(team=self)

    @property
    def name(self):
        return self.full_name

    @property
    def nickname(self):
        return self.short_name


class TeamSeason(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    season = models.ForeignKey(Season, on_delete=models.SET_NULL, blank=True, null=True)
    league = models.ForeignKey(League, on_delete=models.SET_NULL, blank=True, null=True)
    division = models.ForeignKey(Division, on_delete=models.SET_NULL, blank=True, null=True)

    # Performance
    wins = models.IntegerField(blank=True, null=True)
    losses = models.IntegerField(blank=True, null=True)
    division_place = models.IntegerField(blank=True, null=True)
    wild_card = models.BooleanField(default=False)
    won_division = models.BooleanField(default=False)
    won_wild_card = models.BooleanField(default=False)
    won_divisional_series = models.BooleanField(default=False)
    won_league_championship = models.BooleanField(default=False)
    won_world_series = models.BooleanField(default=False)

    # Rosters
    roster_85_man = models.IntegerField(blank=True, null=True)
    roster_40_man = models.IntegerField(blank=True, null=True)
    roster_30_man = models.IntegerField(blank=True, null=True)

    # Financials
    contract_salary = models.IntegerField(blank=True, null=True)
    carried_salary = models.IntegerField(blank=True, null=True)
    cash_borrowing = models.IntegerField(blank=True, null=True)
    cap_space = models.IntegerField(blank=True, null=True)
    luxury_cap_space = models.IntegerField(blank=True, null=True)
    cash = models.IntegerField(blank=True, null=True)
    ifa = models.IntegerField(blank=True, null=True)

    def __unicode__(self):
        return f"{self.season} Season: {self.team}"

class Player(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    is_owned = models.BooleanField(default=False)

    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    name = models.CharField(max_length=255)
    height = models.CharField(max_length=15, blank=True, null=True)
    weight = models.CharField(max_length=3, blank=True, null=True)
    birthdate = models.DateField(blank=True, null=True)
    raw_name = models.CharField(max_length=255, blank=True, null=True)
    raw_age = models.IntegerField(default=None, blank=True, null=True)

    # On the field
    position = models.CharField(max_length=255, blank=True, null=True)
    simple_position = models.CharField(max_length=255, blank=True, null=True)
    bats = models.CharField(max_length=3, blank=True, null=True)
    throws = models.CharField(max_length=3, blank=True, null=True)

    # Scoresheet
    scoresheet_defense = models.JSONField(null=True, blank=True)
    scoresheet_offense = models.JSONField(null=True, blank=True)

    # Identifiers
    mlb_id = models.CharField(max_length=255, primary_key=True)
    scoresheet_id = models.CharField(max_length=255, blank=True, null=True)
    fg_id = models.CharField(max_length=255, blank=True, null=True)
    bp_id = models.CharField(max_length=255, blank=True, null=True)
    bref_id = models.CharField(max_length=255, blank=True, null=True)

    # Real MLB status
    mlb_org = models.CharField(max_length=255, blank=True, null=True)
    roster_status = models.CharField(max_length=255, blank=True, null=True)

    # Contract status
    mls_time = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    mls_year = models.CharField(max_length=255, blank=True, null=True)

    # NPL statuses
    npl_status = models.CharField(max_length=255, blank=True, null=True)

    fg_role_type = models.CharField(max_length=255, blank=True, null=True)
    fg_role = models.CharField(max_length=255, blank=True, null=True)
    fg_injury_description = models.CharField(max_length=255, blank=True, null=True)

    fg_is_injured = models.BooleanField(default=False)
    fg_is_starter = models.BooleanField(default=False)
    fg_is_bench = models.BooleanField(default=False)
    fg_is_mlb40man = models.BooleanField(default=False)

    grad_year = models.IntegerField(default=None, blank=True, null=True)
    service_time = models.DecimalField(max_digits=5, decimal_places=3, blank=True, null=True)
    options = models.IntegerField(default=3, blank=True, null=True)
    has_been_rostered = models.BooleanField(default=False)
    has_been_npl40 = models.BooleanField(default=False)
    has_been_qo = models.BooleanField(default=False)
    has_been_outright = models.BooleanField(default=False)
    roster_85man = models.BooleanField(default=False)
    roster_40man = models.BooleanField(default=False)
    roster_30man = models.BooleanField(default=False)
    roster_7dayIL = models.BooleanField(default=False)
    roster_56dayIL = models.BooleanField(default=False)
    roster_eosIL = models.BooleanField(default=False)
    roster_restricted = models.BooleanField(default=False)
    roster_tripleA = models.BooleanField(default=False)
    roster_tripleA_option = models.BooleanField(default=False)
    roster_outrighted = models.BooleanField(default=False)
    roster_foreign = models.BooleanField(default=False)
    roster_retired = models.BooleanField(default=False)
    roster_nonroster = models.BooleanField(default=False)
    roster_doubleA = models.BooleanField(default=False)
    roster_singleA = models.BooleanField(default=False)
    roster_owaivers = models.BooleanField(default=False)
    roster_r5waivers = models.BooleanField(default=False)
    recall_eligible = models.BooleanField(default=False)
    activation_eligible = models.BooleanField(default=False)
    waiver_clear = models.BooleanField(default=False)
    is_r5 = models.BooleanField(default=False)
    r5_return_team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name="r5_return_team")

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
        ordering = ['team__short_name', '-roster_40man', 'position', 'last_name']

    def __unicode__(self):
        if self.team:
            return f"{self.position} {self.name} {self.mlb_org} ({self.team.short_name})"
        return f"{self.position} {self.name} {self.mlb_org}"

    @property
    def age(self):
        if self.birthdate:
            now = datetime.datetime.utcnow().date()
            return relativedelta(now, self.birthdate).years
        elif self.raw_age:
            return self.raw_age
        return None

    @property
    def get_roster_status(self):
        if self.roster_status == "MLB":
            return "Majors"

        if self.roster_status == "MINORS":
            return "Minors"

        return self.roster_status

    @property
    def get_npl_status(self):
        if self.npl_status == "is_roster_30_man":
            return "MLB 30-man"

        if self.npl_status == "is_roster_aaa_outright":
            return "AAA Outright"

        if self.npl_status == "is_roster_aaa_option":
            return "AAA On Option"

        if self.npl_status == "is_roster_7_day_il":
            return "IL-7"

        return self.npl_status

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
    def get_npl_status(self):
        if self.npl_status == "is_roster_30_man":
            return "MLB 30-man"

        if self.npl_status == "is_roster_aaa_outright":
            return "AAA Outright"

        if self.npl_status == "is_roster_aaa_option":
            return "AAA On Option"

        if self.npl_status == "is_roster_7_day_il":
            return "IL-7"

        return self.npl_status

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

    def set_options(self):
        """
        Options
        """
        if not self.options == 99:
            if self.options > 3:
                self.options = 3

        if not self.options:
            self.options = 3

    def save(self, *args, **kwargs):
        self.set_name()
        self.set_owned()
        self.set_simple_position()
        self.set_options()

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

        if self.stats:
            for year_side_level, stats in self.stats.items():
                if stats['side'] == "pitch":
                    if stats['g'] >= 1:
                        payload.append(stats)

        payload = sorted(payload, key=lambda x:int(x['year']))

        return payload

    def hit_stats(self):
        # shoudl return stats dict by level and year
        payload = []

        if self.stats:
            for year_side_level, stats in self.stats.items():
                if stats['side'] == "hit":
                    if stats['plate_appearances'] >= 1:
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
            try:
                self.player = Player.objects.get(mlb_id=self.mlb_id)
            except:
                pass

    def set_team(self):
        if self.raw_team and not self.team:
            team = self.raw_team
            if self.raw_team == "Hyperjets":
                team = "DockHounds"
            try:
                self.team = Team.objects.get(short_name__icontains=team)

            except Team.DoesNotExist:
                pass 

    def set_acquiring_team(self):
        if self.raw_acquiring_team and not self.acquiring_team:
            team = self.raw_acquiring_team
            if self.raw_team == "Hyperjets":
                team = "DockHounds"
            try:
                self.acquiring_team = Team.objects.get(short_name__icontains=team)

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

class DraftPick(BaseModel):
    AA_TYPE = "aa"
    OPEN_TYPE = "open"
    BALANCE_TYPE = "balance"
    DRAFT_TYPE_CHOICES = (
        (AA_TYPE, "aa"),
        (OPEN_TYPE, "open"),
        (BALANCE_TYPE, "balance"),
    )
    draft_type = models.CharField(max_length=255, choices=DRAFT_TYPE_CHOICES, null=True)
    draft_round = models.IntegerField(null=True)
    year = models.CharField(max_length=4)
    pick_number = models.IntegerField(null=True, blank=True)
    overall_pick_number = models.IntegerField(null=True, blank=True)
    OFFSEASON = "offseason"
    MIDSEASON = "midseason"
    SEASON_CHOICES = (
        (OFFSEASON, "offseason"),
        (MIDSEASON, "midseason"),
    )
    season = models.CharField(max_length=255, choices=SEASON_CHOICES)
    slug = models.CharField(max_length=255, null=True, blank=True)
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, blank=True, null=True, related_name="draftpick_team"
    )
    team_name = models.CharField(max_length=255, blank=True, null=True)
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    player_name = models.CharField(max_length=255, blank=True, null=True)
    pick_notes = models.TextField(blank=True, null=True)
    original_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="original_team",
    )
    skipped = models.BooleanField(default=False)

    class Meta:
        ordering = ["-year", "-season", "draft_type", "draft_round", "pick_number"]

    def __unicode__(self):
        return "%s %s %s (%s)" % (self.year, self.season, self.slug, self.team)

    def to_api_obj(self):
        payload = {}
        payload['draft_type'] = self.draft_type
        payload['draft_round'] = self.draft_round
        payload['year'] = self.year
        payload['pick_number'] = self.pick_number
        payload['overall_pick_number'] = self.overall_pick_number
        payload['season'] = self.season
        payload['slug'] = self.slug
        payload['team_name'] = self.team_name
        payload['player_name'] = self.player_name
        payload['skipped'] = self.skipped
        payload['original_team'] = None
        payload['team'] = None
        payload['player'] = None

        if self.original_team:
            payload['original_team'] = self.original_team.to_api_obj()

        if self.team:
            payload['team'] = self.team.to_api_obj()

        if self.player:
            payload['player'] = self.player.to_api_obj()

        return payload

    def slugify(self):
        if self.draft_type == "aa":
            dt = "AA"

        if self.draft_type == "open":
            dt = "OP"

        if self.draft_type == "balance":
            dt = "CB"

        self.slug = f"{self.original_team} {dt}{self.draft_round}"
        if self.player:
            self.slug = (
                f"{self.original_team} {dt}{self.draft_round} ({self.player.name})"
            )

    def set_overall_pick_number(self):
        if self.pick_number:
            rnd = self.draft_round - 1
            self.overall_pick_number = self.pick_number + (rnd * 16)

    def set_original_team(self):
        if not self.original_team and self.team:
            self.original_team = self.team

    def set_player_name(self):
        if self.player:
            self.player_name = self.player.name

    def save(self, *args, **kwargs):
        ## Need to comment this part out if saving archived draft picks
        ## that have a player name only but not a player object
        ## so that players are not swapped to a different team.
        if self.player and self.team:
            if not self.player.team:
                self.player.team = self.team
                self.player.save()

            if self.player.team and self.player.team != self.team:
                self.player.team = self.team
                self.player.save()

        self.set_original_team()
        self.set_overall_pick_number()
        self.slugify()
        self.set_player_name()

        super().save(*args, **kwargs)


class Trade(BaseModel):
    """
    On the frontend, there will just be two slots for teams
    and then slots for players and picks that can be selected from.
    On save, the view will create the Trade object and then two
    related TradeReceipt objects containing the players and picks.
    """

    date = models.DateField()
    season = models.IntegerField(blank=True, null=True)
    trade_summary = models.TextField(blank=True, null=True)
    trade_cache = models.JSONField(blank=True, null=True)
    teams = models.ManyToManyField(Team, blank=True)

    def __unicode__(self):
        return self.summary()

    def set_season(self):
        self.season = utils.get_ulmg_season(self.date)

    def set_teams(self):
        if self.reciepts():
            for r in self.reciepts():
                self.teams.add(r.team)

    def set_trade_summary(self):
        if self.reciepts():
            cache = {}

            t1 = self.reciepts()[0]
            t2 = self.reciepts()[1]

            cache[t1.team.abbreviation.lower()] = t1
            cache[t2.team.abbreviation.lower()] = t2

            self.trade_cache = self.summary_dict()

    def save(self, *args, **kwargs):
        self.set_season()
        super().save(*args, **kwargs)

    def reciepts(self):
        return TradeReceipt.objects.filter(trade=self)

    def summary_html(self):
        t1 = self.reciepts()[0]
        t2 = self.reciepts()[1]

        return "<td>%s</td><td style='text-align: left;'>%s</td><td>%s</td><td style='text-align: left;'>%s</td><td>%s</td>" % (
            self.date,
            "<a href='/teams/%s/'>%s</a>"
            % (t1.team.abbreviation.lower(), t1.team.abbreviation),
            ", ".join(
                [
                    "%s <a href='/players/%s/'>%s</a>" % (p.position, p.id, p.name)
                    for p in t2.players.all()
                ]
                + [f"{p.year} {p.season } {p.slug}" for p in t2.picks.all()]
            ),
            "<a href='/teams/%s/'>%s</a>"
            % (t2.team.abbreviation.lower(), t2.team.abbreviation),
            ", ".join(
                [
                    "%s <a href='/players/%s/'>%s</a>" % (p.position, p.id, p.name)
                    for p in t1.players.all()
                ]
                + [f"{p.year} {p.season } {p.slug}" for p in t1.picks.all()]
            ),
        )

    def summary_dict(self):
        t1 = self.reciepts()[0]
        t2 = self.reciepts()[1]

        return {
            "date": f"{self.date.year}-{self.date.month}-{self.date.day}",
            "t1_abbr": t1.team.abbreviation,
            "t1_players": [
                {"pos": p.position, "name": p.name, "id": p.id}
                for p in t2.players.all()
            ],
            "t1_picks": [f"{p.slug}" for p in t2.picks.all()],
            "t2_abbr": t2.team.abbreviation,
            "t2_players": [
                {"pos": p.position, "name": p.name, "id": p.id}
                for p in t1.players.all()
            ],
            "t2_picks": [f"{p.slug}" for p in t1.picks.all()],
        }

    def summary(self):
        t1 = self.reciepts()[0]
        t2 = self.reciepts()[1]

        return "%s: %s sends %s to %s for %s" % (
            self.date,
            t1.team.abbreviation,
            ", ".join(
                ["%s %s" % (p.position, p.name) for p in t2.players.all()]
                + [f"{p.slug}" for p in t2.picks.all()]
            ),
            t2.team.abbreviation,
            ", ".join(
                ["%s %s" % (p.position, p.name) for p in t1.players.all()]
                + [f"{p.year} {p.season } {p.slug}" for p in t1.picks.all()]
            ),
        )


class TradeReceipt(BaseModel):
    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name="tradereceipt_team")
    players = models.ManyToManyField(Player, related_name="players", blank=True)
    picks = models.ManyToManyField(DraftPick, related_name="picks", blank=True)

    def __unicode__(self):
        if self.trade:
            return "Trade %s: %s" % (self.trade.id, self.team)
        return self.team.abbreviation

    def summary(self):
        return ", ".join(
            ["%s %s" % (p.position, p.name) for p in self.players.all()]
            + [f"{p.slug}" for p in self.picks.all()]
        )

    def summary_html(self):
        return ", ".join(
            [
                "<a class='has-text-weight-semibold' href='/players/%s/'>%s %s</a>"
                % (p.id, p.position, p.name)
                for p in self.players.all()
            ]
            + [f"{p.slug}" for p in self.picks.all()]
        )

    @staticmethod
    def set_team(sender, instance, action, reverse, model, pk_set, **kwargs):
        team = instance.team
        trade = instance.trade
        trade.teams.add(team)
        trade.save()

    @staticmethod
    def trade_pick(sender, instance, action, reverse, model, pk_set, **kwargs):

        # when loading fixtures, do not try to update the team reference for a pick
        if not os.environ.get("ULMG_FIXTURES", None):
            if action == "post_add":
                team = instance.team
                for p in pk_set:
                    obj = DraftPick.objects.get(id=p)
                    obj.team = instance.team
                    obj.save()

    @staticmethod
    def trade_player(sender, instance, action, reverse, model, pk_set, **kwargs):

        # when loading fixtures, do not try to update the team reference for a player
        if not os.environ.get("ULMG_FIXTURES", None):
            if action == "post_add":
                team = instance.team
                for p in pk_set:
                    obj = Player.objects.get(id=p)
                    obj.is_reserve = False
                    obj.is_1h_c = False
                    obj.is_1h_p = False
                    obj.is_1h_pos = False
                    obj.is_2h_c = False
                    obj.is_2h_p = False
                    obj.is_2h_pos = False
                    obj.is_35man_roster = False
                    obj.is_mlb = False
                    obj.is_aaa_roster = False
                    obj.is_protected = False
                    obj.is_owned = True
                    obj.team = instance.team
                    obj.save()


m2m_changed.connect(
    receiver=TradeReceipt.trade_player, sender=TradeReceipt.players.through
)
m2m_changed.connect(receiver=TradeReceipt.trade_pick, sender=TradeReceipt.picks.through)


class TradeSummary(BaseModel):
    season = models.CharField(max_length=255, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    PLAYERS = "players only"
    PICKS = "players and picks"
    TRADE_TYPE_CHOICES = (
        (PLAYERS, "players only"),
        (PICKS, "players and picks"),
    )
    trade_type = models.CharField(max_length=255, choices=TRADE_TYPE_CHOICES)

    def __unicode__(self):
        return "%s: %s (%s)" % (self.season, self.trade_type, self.pk)

    class Meta:
        ordering = ["-season", "trade_type"]


class Wishlist(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="wishlist_team")

    def __unicode__(self):
        return f"{self.team}"


class WishlistPlayer(BaseModel):
    """
    Denormalized player record for wishlists
    """
    COL_LVL = "COL"
    HS_LVL = "HS"
    MLB_LVL = "MLB"
    MINOR_LVL = "MINORS"
    NPB_LVL = "NPB"
    KBO_LVL = "KBO"
    INTAM_LVL = "INT-AM"
    PLAYER_LEVEL_CHOICES = (
        (COL_LVL, "col"),
        (HS_LVL, "hs"),
        (MLB_LVL, "mlb"),
        (MINOR_LVL, "minors"),
        (NPB_LVL, "npb"),
        (KBO_LVL, "kbo"),
        (INTAM_LVL, "int-am"),
    )

    PRO_TYPE = "PRO"
    AM_TYPE = "AM"
    INT_TYPE = "INT"
    PLAYER_TYPE_CHOICES = (
        (PRO_TYPE, "pro"),
        (AM_TYPE, "am"),
        (INT_TYPE, "int"),
    )

    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE)
    rank = models.IntegerField(blank=True, null=True)
    tier = models.IntegerField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    tags = ArrayField(models.CharField(max_length=255), blank=True, null=True)
    player_type = models.CharField(max_length=255, choices=PLAYER_TYPE_CHOICES, blank=True, null=True)
    player_school = models.CharField(max_length=255, blank=True, null=True)
    player_level = models.CharField(max_length=255, choices=PLAYER_LEVEL_CHOICES, blank=True, null=True)
    player_year = models.IntegerField(blank=True, null=True)
    player_fv = models.IntegerField(blank=True, null=True)
    player_risk = models.IntegerField(blank=True, null=True)
    interesting = models.BooleanField(default=False)

    stats = models.JSONField(null=True, blank=True)

    def __unicode__(self):
        return f"{self.player} [{self.rank}]"

    @property
    def owner_name(self):
        return self.wishlist.owner.name

    def save(self, *args, **kwargs):
        self.stats = self.player.stats

        super().save(*args, **kwargs)

    class Meta:
        ordering = ['wishlist', 'rank', 'player']