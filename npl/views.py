import csv
import datetime
import itertools

import django.core.exceptions
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Sum, Max, Min, Q
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from decimal import *

import ujson as json
from datetime import datetime
import pytz

from npl import models, utils

def auction_bid_api(request, auctionid):
    now = datetime.now(pytz.timezone('US/Eastern'))
    payload = {
        "message": None,
        "success": False,
        "auction": {
            "is_mlb_auction": None,
            "closes": None,
            "player": None
        },
        "bid": None,
        "bid_team": None,
        "bid_team_nick": None,
        "leading_bid": None,
        "leading_bid_team": None,
        "leading_bid_team_nick": None,
        "max_bid": None,
        "max_bid_team": None,
        "max_bid_team_nick": None,
    }
    context = utils.build_context(request)
    context['time'] = now

    # return a 404 if there's no matching auction
    auction = get_object_or_404(models.Auction, pk=auctionid)

    # auction is still alive and there is an active owner with an associated team
    if auction.closes >= now and context['owner'] and context['team'] and auction.active:

        payload['auction']['player'] = auction.player.name
        payload['auction']['closes'] = auction.closes
        payload['auction']['is_mlb_auction'] = auction.is_mlb_auction
        payload['bid'] = request.GET.get('bid', None)

        payload['max_bid'] = auction.max_bid()['bid']
        payload['max_bid_team'] = auction.max_bid()['team_id']
        payload['max_bid_team_nick'] = auction.max_bid()['team_nick']

        payload['leading_bid'] = auction.leading_bid()['bid']
        payload['leading_bid_team'] = auction.leading_bid()['team_id']
        payload['leading_bid_team_nick'] = auction.max_bid()['team_nick']

        payload['bid_team'] = context['team'].pk
        payload['bid_team_nick'] = context['team'].nickname

        # determine if this is an MLB or NonMLB auction bid
        if auction.is_mlb_auction:
            obj = models.MLBAuctionBid
            payload['bid'] = int(payload['bid'])            
        else:
            obj = models.NonMLBAuctionBid
            payload['bid'] = Decimal(payload['bid'])

        # find the bid, and increase the bid only, no decreases
        # no bid? create one.
        try:
            obj = obj.objects.get(auction=auction, team=context['team'])
            if obj.max_bid <= payload['bid']:
                obj.max_bid = payload['bid']
                obj.save()

        except models.MLBAuctionBid.DoesNotExist:
            obj = models.MLBAuctionBid(max_bid=payload['bid'], auction=auction, team=context['team'])
            obj.save()
        
        except models.NonMLBAuctionBid.DoesNotExist:
            obj = models.NonMLBAuctionBid(max_bid=payload['bid'], auction=auction, team=context['team'])
            obj.save()

        # get the newest state for the auction and its bids
        payload['max_bid'] = auction.max_bid()['bid']
        payload['max_bid_team'] = auction.max_bid()['team_id']
        payload['max_bid_team_nick'] = auction.max_bid()['team_nick']

        payload['leading_bid'] = auction.leading_bid()['bid']
        payload['leading_bid_team'] = auction.leading_bid()['team_id']
        payload['leading_bid_team_nick'] = auction.max_bid()['team_nick']

        # before we return a message, evaluate the bids
        if payload['max_bid_team'] == context['team'].pk:
            if payload['max_bid'] <= payload['bid']:
                payload['message'] = f"{payload['bid_team_nick']} has set a higher max bid of ${payload['bid']} on {auction.player.name}. The leading bid is still ${payload['leading_bid']}."
                payload['success'] = True 
            else:
                payload['message'] = f"Your bid of ${payload['bid']} is less than an earlier max bid by {payload['bid_team_nick']} of ${payload['max_bid']} on {auction.player.name}. The leading bid is still ${payload['leading_bid']}."
                payload['success'] = True 
        
        elif payload['bid'] > payload['max_bid']:
            # you have the high bid
            payload['message'] = f"{payload['bid_team_nick']} has set a max bid ${payload['bid']} on {auction.player.name}. The leading bid is now ${payload['leading_bid']}."
            payload['success'] = True 
            
        else:
            # you do not have the high bid
            payload['message'] = f"{payload['bid_team_nick']} bid ${payload['bid']} on {auction.player.name} which does not exceed the leading bid of ${payload['leading_bid']}."

    else:
        if auction.closes < now:
            payload['message'] = "Bidding for this auction has ended."
        else:
            payload['message'] = "This bid was not cast by an owner of an NPL team."

    return JsonResponse(payload)

def auction_list(request):
    context = utils.build_context(request)
    context['time'] = datetime.now(pytz.timezone('US/Eastern'))
    context['auctions'] = models.Auction.objects.filter(closes__gte=context['time'], active=True)
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
    team = get_object_or_404(models.Team, nickname__icontains=nickname)
    context["team"] = team
    context["is_owner"] = utils.is_user_owner(request, team)

    team_players = models.Player.objects.filter(team=team)
    context['total_count'] = team_players.count()
    context['roster_40_man_count'] = team_players.filter(is_roster_40_man=True).count()
    context['hitters'] = team_players.exclude(simple_position="P").order_by('simple_position', '-is_roster_40_man', '-mls_time', 'mls_year')
    context['pitchers'] = team_players.filter(simple_position="P").order_by('-is_roster_40_man', '-mls_time', 'mls_year')
    return render(request, "team.html", context)

def transactions(request):
    context = utils.build_context(request)
    context['transactions'] = models.Transaction.objects.all()

    return render(request, 'transactions.html', context)

def waivers(request):
    now = datetime.now(tz=pytz.timezone("US/Eastern"))
    context = utils.build_context(request)
    outrighted = models.Player.objects.filter(is_on_outright_waivers=True)
    context['outrighted'] = outrighted
    context['is_waivers'] = True
    if request.method == 'POST':
        players_claimed = request.POST.getlist('outright_claims')
        team = utils.get_team_making_request(request)

        for player in players_claimed:
            outright_claim = models.OutrightWaiverClaim()
            outright_claim.team = team
            outright_claim.player = models.Player.objects.filter(mlb_id=player).get()
            outright_claim.submission_time = now
            outright_claim.deadline = utils.calculate_next_friday_at_one_pm_eastern(now)
            outright_claim.save()

    return render(request, "waivers.html", context)
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