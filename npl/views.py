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
            "closes": None,
            "player": None
        },
    }
    context = utils.build_context(request)
    context['time'] = now

    # return a 404 if there's no matching auction
    auction = get_object_or_404(models.Auction, pk=auctionid)

    # auction is still alive and there is an active owner with an associated team
    if auction.closes >= now and context['owner'] and context['owner_team'] and auction.active:

        payload['auction']['player'] = auction.player.name
        payload['auction']['closes'] = auction.closes
        payload['bid'] = request.GET.get('bid', None)

        obj = models.MLBAuctionBid
        payload['bid'] = int(payload['bid'])

        # find the bid, but you can only bid once.
        # no bid? create one.
        try:
            obj = obj.objects.get(auction=auction, team=context['owner_team'])
            payload['message'] = "Naughty, you've already bid on this auction! Are we reverse engineering the API?"

            return JsonResponse(payload)

        except models.MLBAuctionBid.DoesNotExist:
            obj = models.MLBAuctionBid(max_bid=payload['bid'], auction=auction, team=context['owner_team'])
            obj.save()

        # get the newest state for the auction and its bids
        payload['max_bid'] = auction.max_bid()['bid']
        payload['max_bid_team'] = auction.max_bid()['team_id']

        payload['leading_bid'] = auction.leading_bid()['bid']
        payload['leading_bid_team'] = auction.leading_bid()['team_id']

        if payload['bid'] <= payload['max_bid']:
            # you have failed to have the highest bid
            payload['message'] = f"Your bid of ${payload['bid']} on {auction.player.name} does not exceed the maximum bid."
        
        elif payload['bid'] > payload['max_bid']:
            # you have the highest bid
            payload['message'] = f"You now have the leading bid of ${payload['bid']} on {auction.player.name} with a maximum bid of ${payload['max_bid']}."

    else:
        if auction.closes < now:
            payload['message'] = "Bidding for this auction has ended."
        else:
            payload['message'] = "This bid was not cast by an owner of an NPL team."

    return JsonResponse(payload)

def auction_list(request):
    context = utils.build_context(request)
    context['time'] = datetime.now(pytz.timezone('US/Eastern'))
    context['auctions'] = []
    for a in models.Auction.objects.filter(closes__gte=context['time'], active=True):
        try:
            m = models.MLBAuctionBid.objects.get(auction=a, team=context['owner_team'])
            a.can_bid = False
        except models.MLBAuctionBid.DoesNotExist:
            a.can_bid = True
            a.minimum_bid_price = a.leading_bid()['bid'] + 1
        context['auctions'].append(a)
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

def team_detail(request, short_name):
    context = utils.build_context(request)
    context["team"] = get_object_or_404(models.Team, short_name__icontains=short_name)

    team_players = models.Player.objects.filter(team=context["team"])
    context['total_count'] = team_players.count()
    context['roster_40_man_count'] = team_players.filter(roster_40man=True).count()
    context['roster_30_man_count'] = team_players.filter(roster_30man=True).count()
    context['hitters'] = team_players.exclude(simple_position="P").order_by('simple_position','-mls_time', 'mls_year')
    context['pitchers'] = team_players.filter(simple_position="P").order_by('-mls_time', 'mls_year')
    context['mlb_hitters'] = team_players.exclude(simple_position="P").exclude(roster_40man=False).order_by('simple_position','-mls_time', 'mls_year')
    context['mlb_pitchers'] = team_players.filter(simple_position="P", roster_40man=True).order_by('-mls_time', 'mls_year')
    context['aaa_pitchers'] = team_players.filter(simple_position="P", roster_tripleA=True).order_by('-mls_time', 'mls_year')
    context['aaa_hitters'] = team_players.exclude(simple_position="P").filter(roster_tripleA=True).order_by('-mls_time', 'mls_year')
    context['aa_pitchers'] = team_players.filter(simple_position="P", roster_doubleA=True).order_by('-mls_time', 'mls_year')
    context['aa_hitters'] = team_players.exclude(simple_position="P").filter(roster_doubleA=True).order_by('-mls_time', 'mls_year')
    context['a_pitchers'] = team_players.filter(simple_position="P", roster_singleA=True).order_by('-mls_time', 'mls_year')
    context['a_hitters'] = team_players.exclude(simple_position="P").filter(roster_singleA=True).order_by('-mls_time', 'mls_year')
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

    if request.GET.get("roster_status", None):
        roster_status = request.GET['roster_status']
        if roster_status.lower() != "":
            query = query.filter(roster_status=roster_status.upper())
            context['roster_status'] = roster_status

    context['total_count'] = query.count()
    context["hitters"] = query.exclude(simple_position="P").order_by("simple_position", "last_name")
    context["pitchers"] = query.filter(simple_position="P").order_by("last_name")
    return render(request, "search.html", context)

@login_required
def my_wishlist(request):
    context = utils.build_context(request)
    context["wishlist"] = models.Wishlist.objects.get(team=context["owner_team"])

    # context['my_open_picks'] = models.DraftPick.objects.filter(team=context['team'], year=2025, season="offseason", draft_type="open")
    # context['all_open_picks'] = models.DraftPick.objects.filter(year=2025, season="offseason", draft_type="open").values('overall_pick_number', 'team__abbreviation')
 
    context["players"] = models.WishlistPlayer.objects.filter(
        wishlist=context["wishlist"], player__is_owned=False
    ).order_by("rank", "interesting")

    context['my_picks'] = [37, 59, 107, 131, 155]

    # context["tags"] = set()

    # for p in context["players"].values("tags"):
    #     if p["tags"]:
    #         for z in p["tags"]:
    #             context["tags"].add(z)

    # context["tags"] = sorted(list(context["tags"]), key=lambda x: x)
    # context["num_owned"] = models.Player.objects.filter(team=context["team"]).count()

    return render(request, "my/wishlist.html", context)

@csrf_exempt
@login_required
def wishlist_bulk(request):
    context = utils.build_context(request)
    wishlist = None
    wl = models.Wishlist.objects.filter(team=context["owner_team"])
    if len(wl) > 0:
        wishlist = wl[0]

    for raw_json_string, _ in request.POST.items():
        players = json.loads(raw_json_string)
        for p in players:
            models.WishlistPlayer.objects.filter(wishlist=wishlist, player__mlb_id=p["playerid"]).update(
                rank=p["rank"]
            )

    return JsonResponse({"success": True, "updated": len(players)})

@csrf_exempt
@login_required
def interesting_action(request, playerid):
    context = utils.build_context(request)
    wl = models.Wishlist.objects.get(team=context["owner_team"])
    pl = models.Player.objects.get(mlb_id=playerid)
    w = models.WishlistPlayer.objects.get(wishlist=wl, player=pl)

    action = request.GET.get("action").strip()

    if action == "add":
        w.interesting = True

    elif action == "remove":
        w.interesting = False

    w.save()
    print(w.interesting)
    return JsonResponse({"success": True, 'player': w.player.name, 'interesting': w.interesting})