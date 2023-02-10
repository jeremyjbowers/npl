import datetime
import os

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
        ordering = ["league", "division", "name"]

    def __unicode__(self):
        return self.name

    # def players(self):
    #     return Player.objects.filter(team=self)