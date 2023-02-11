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
    context['players'] = unowned_players.order_by("last_name", "first_name")
    return render(request, "index.html", context)

def player_detail(request, playerid):
    context = utils.build_context(request)
    context['p'] = get_object_or_404(models.Player, mlb_id=playerid)
    return render(request, "player.html", context)

def team_detail(request, nickname):
    context = utils.build_context(request)
    context["team"] = get_object_or_404(models.Team, nickname__icontains=nickname)

    team_players = models.Player.objects.filter(team=context["team"])
    context['players'] = team_players.order_by('-is_roster_40_man', 'position', 'last_name')
    return render(request, "team.html", context)