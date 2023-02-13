import csv
import datetime
import itertools
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Sum, Max, Min, Q
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required

import ujson as json
from datetime import datetime

from npl import models, utils

def index(request):
    context = utils.build_context(request)
    unowned_players = models.Player.objects.filter(team__isnull=True)
    context['pitchers'] = unowned_players.filter(simple_position="P").order_by('-is_roster_40_man', '-mls_time', 'mls_year')
    context['hitters'] = unowned_players.exclude(simple_position="P").order_by('simple_position', '-is_roster_40_man', '-mls_time', 'mls_year')
    return render(request, "index.html", context)

def player_detail(request, playerid):
    context = utils.build_context(request)
    context['p'] = get_object_or_404(models.Player, mlb_id=playerid)
    return render(request, "player.html", context)

def team_detail(request, nickname):
    context = utils.build_context(request)
    context["team"] = get_object_or_404(models.Team, nickname__icontains=nickname)

    team_players = models.Player.objects.filter(team=context["team"])
    context['hitters'] = team_players.exclude(simple_position="P").order_by('simple_position', '-is_roster_40_man', '-mls_time', 'mls_year')
    context['pitchers'] = team_players.filter(simple_position="P").order_by('-is_roster_40_man', '-mls_time', 'mls_year')
    return render(request, "team.html", context)

def search(request):
    def to_bool(b):
        if b.lower() in ["y", "yes", "t", "true", "on"]:
            return True
        return False

    context = utils.build_context(request)

    query = models.Player.objects.all()

    if request.GET.get("name", None):
        name = request.GET["name"]
        query = query.filter(name__icontains=name)
        context["name"] = name

    if request.GET.get("position", None):
        position = request.GET["position"]
        if position.lower() not in ["", "h", "p"]:
            query = query.filter(simple_position__icontains=position)
            context["position"] = position
        elif position.lower() == "h":
            query = query.exclude(simple_position="P")
            context["position"] = position
        elif position.lower() == "p":
            query = query.filter(simple_position="P")
            context["position"] = position

    if request.GET.get("owned", None):
        owned = request.GET["owned"]
        if owned.lower() != "":
            query = query.filter(is_owned=to_bool(owned))
            context["owned"] = owned

    query = query.order_by("position", "last_name")

    context["hitters"] = query.exclude(simple_position="P")
    context["pitchers"] = query.filter(simple_position="P")
    return render(request, "search.html", context)