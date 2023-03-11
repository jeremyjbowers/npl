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
import pytz

from npl import models, utils

def auction_list(request):
    context = utils.build_context(request)
    context['time'] = datetime.now(pytz.timezone('US/Eastern'))
    context['auctions'] = models.Auction.objects.filter(closes__gte=context['time'])
    return render(request, "auction_list.html", context)

def npl_page_list(request):
    context = utils.build_context(request)
    context['pages'] = models.Page.objects.filter(active=True).order_by('-collection__name, title')
    return render(request, "page_list.html", context)

def npl_page_detail(request, slug):
    context = utils.build_context(request)
    context['page'] = get_object_or_404(models.Page, slug=slug)
    return render(request, "page_detail.html", context)

def index(request):
    context = utils.build_context(request)
    unowned_players = models.Player.objects.filter(team__isnull=True)
    context['total_count'] = unowned_players.count()
    context['pitchers'] = unowned_players.filter(simple_position="P").order_by('last_name')
    context['hitters'] = unowned_players.exclude(simple_position="P").order_by('simple_position', 'last_name')
    context['events'] = models.Event.objects.filter(active=True).order_by('date')[:8]
    context['transactions'] = models.Transaction.objects.all().order_by('-date', 'transaction_type')[:15]
    return render(request, "index.html", context)

def player_detail(request, playerid):
    context = utils.build_context(request)
    context['p'] = get_object_or_404(models.Player, mlb_id=playerid)
    return render(request, "player.html", context)

def team_detail(request, nickname):
    context = utils.build_context(request)
    context["team"] = get_object_or_404(models.Team, nickname__icontains=nickname)

    team_players = models.Player.objects.filter(team=context["team"])
    context['total_count'] = team_players.count()
    context['roster_40_man_count'] = team_players.filter(is_roster_40_man=True).count()
    context['hitters'] = team_players.exclude(simple_position="P").order_by('simple_position', '-is_roster_40_man', '-mls_time', 'mls_year')
    context['pitchers'] = team_players.filter(simple_position="P").order_by('-is_roster_40_man', '-mls_time', 'mls_year')
    return render(request, "team.html", context)

def transactions(request):
    context = utils.build_context(request)
    context['transactions'] = models.Transaction.objects.all()

    return render(request, 'transactions.html', context)

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

    context['total_count'] = query.count()
    context["hitters"] = query.exclude(simple_position="P").order_by("simple_position", "last_name")
    context["pitchers"] = query.filter(simple_position="P").order_by("last_name")
    return render(request, "search.html", context)