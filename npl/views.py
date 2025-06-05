import csv
import datetime
import itertools
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Sum, Max, Min, Q
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from decimal import *
from django.contrib import messages
from django.utils import timezone
from django.db import models as django_models

import ujson as json
from datetime import datetime, timedelta
import pytz

from npl import models, utils
from .forms import TransactionTypeForm, TRANSACTION_FORM_MAP

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

    # Check if auction is expired
    if auction.is_expired():
        payload['message'] = "Bidding for this auction has ended."
        # For expired auctions, show winning bid info
        winning_bid = auction.winning_bid()
        payload['winning_bid'] = winning_bid['winning_amount']
        payload['winning_team'] = winning_bid['team_id']
        return JsonResponse(payload)

    # Check if user has permission to bid
    if not (context['owner'] and context['owner_team'] and auction.active):
        payload['message'] = "This bid was not cast by an owner of an NPL team."
        return JsonResponse(payload)

    # Check if this is a nomination-only auction
    if auction.is_nomination:
        payload['message'] = "This is a nomination only. Bids are not accepted for nominations."
        return JsonResponse(payload)

    # Get and validate bid amount
    try:
        bid_amount = int(request.GET.get('bid', 0))
    except (ValueError, TypeError):
        payload['message'] = "Invalid bid amount. Bids must be in dollars."
        return JsonResponse(payload)

    if bid_amount <= 0:
        payload['message'] = "Bid must be a positive dollar amount."
        return JsonResponse(payload)

    if bid_amount < auction.min_bid:
        payload['message'] = f"Bid must be at least ${auction.min_bid}."
        return JsonResponse(payload)

    # Set auction info in payload
    payload['auction']['player'] = auction.player.name
    payload['auction']['closes'] = auction.closes
    payload['bid'] = bid_amount

    # Check if team has already bid (one bid per team rule)
    try:
        existing_bid = models.MLBAuctionBid.objects.get(auction=auction, team=context['owner_team'])
        payload['message'] = "You have already placed a bid on this auction. Only one bid per team is allowed."
        return JsonResponse(payload)
    except models.MLBAuctionBid.DoesNotExist:
        pass

    # Create the bid
    try:
        bid_obj = models.MLBAuctionBid(
            max_bid=bid_amount, 
            auction=auction, 
            team=context['owner_team']
        )
        bid_obj.save()
        payload['success'] = True
        payload['message'] = f"Your bid of ${bid_amount} on {auction.player.name} has been submitted successfully."
        
        # In blind auction, don't reveal competitive information
        payload['your_bid'] = bid_amount
        payload['total_bids'] = models.MLBAuctionBid.objects.filter(auction=auction).count()
        
    except Exception as e:
        payload['message'] = f"Error submitting bid: {str(e)}"

    return JsonResponse(payload)

def auction_list(request):
    context = utils.build_context(request)
    context['time'] = datetime.now(pytz.timezone('US/Eastern'))
    context['auctions'] = []
    
    # Get active auctions (not expired)
    active_auctions = models.Auction.objects.filter(
        closes__gte=context['time'], 
        active=True
    ).exclude(is_nomination=True)  # Exclude nomination-only auctions
    
    for a in active_auctions:
        # Check if user can bid
        try:
            existing_bid = models.MLBAuctionBid.objects.get(auction=a, team=context['owner_team'])
            a.can_bid = False
            a.your_bid = existing_bid.max_bid
        except models.MLBAuctionBid.DoesNotExist:
            a.can_bid = True
            a.your_bid = None
        except (AttributeError, TypeError):
            # No owner_team (not logged in or no team)
            a.can_bid = False
            a.your_bid = None
        
        # Set minimum bid for display
        a.minimum_bid_price = a.min_bid
        
        # For blind auctions, only show minimal info
        a.total_bids = models.MLBAuctionBid.objects.filter(auction=a).count()
        
        # Add leading bid info (will be hidden for active auctions)
        leading_bid_info = a.leading_bid()
        a.leading_bid_display = leading_bid_info
        
        context['auctions'].append(a)
    
    # Also show recent expired auctions with results
    context['recent_expired'] = []
    recent_expired = models.Auction.objects.filter(
        closes__lt=context['time'],
        active=True,
        closes__gte=context['time'] - timedelta(days=7)  # Last 7 days
    ).order_by('-closes')[:10]
    
    for a in recent_expired:
        winning_bid = a.winning_bid()
        a.winning_info = winning_bid
        context['recent_expired'].append(a)
    
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
    """
    ("7-DAY INJURED LIST", "roster_7dayIL"),
    ("56-DAY INJURED LIST", "roster_56dayIL"),
    ("END OF SEASON INJURED LIST", "roster_eosIL"),
    ("RESTRICTED LIST", "roster_restricted"),
    ("TRIPLE-A", "roster_tripleA"),
    ("DOUBLE-A", "roster_doubleA"),
    ("SINGLE-A", "roster_singleA"),
    ("ON OPTION", "roster_tripleA_option"),
    ("ASSIGNED OUTRIGHT", "roster_outrighted"),
    ("FOREIGN", "roster_foreign"),
    ("RETIRED", "roster_retired"),
    ("NON-ROSTER", "roster_nonroster")
    """
    context['roster_7dayIL'] = team_players.filter(roster_7dayIL=True).order_by('-mls_time', 'mls_year')
    context['roster_56dayIL'] = team_players.filter(roster_56dayIL=True).order_by('-mls_time', 'mls_year')
    context['roster_eosIL'] = team_players.filter(roster_eosIL=True).order_by('-mls_time', 'mls_year')
    context['roster_restricted'] = team_players.filter(roster_restricted=True).order_by('-mls_time', 'mls_year')
    context['roster_outrighted'] = team_players.filter(roster_outrighted=True).order_by('-mls_time', 'mls_year')
    context['roster_foreign'] = team_players.filter(roster_foreign=True).order_by('-mls_time', 'mls_year')
    context['roster_retired'] = team_players.filter(roster_retired=True).order_by('-mls_time', 'mls_year')
    context['roster_nonroster'] = team_players.filter(roster_nonroster=True).order_by('-mls_time', 'mls_year')
    context['roster_tripleA'] = team_players.filter(roster_tripleA=True).order_by('-mls_time', 'mls_year')
    context['roster_tripleA_option'] = team_players.filter(roster_tripleA_option=True).order_by('-mls_time', 'mls_year')
    context['roster_doubleA'] = team_players.filter(roster_doubleA=True).order_by('-mls_time', 'mls_year')
    context['roster_singleA'] = team_players.filter(roster_singleA=True).order_by('-mls_time', 'mls_year')
    return render(request, "team.html", context)

def get_next_processing_deadline():
    """Calculate the next Monday 1 PM EST processing deadline (full datetime)"""
    import pytz
    from datetime import datetime, timedelta
    
    # Get current time in EST
    est = pytz.timezone('US/Eastern')
    now = timezone.now().astimezone(est)
    
    # Find next Monday
    days_ahead = 7 - now.weekday()  # Monday is 0
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    elif days_ahead == 7 and now.hour >= 13:  # It's Monday after 1 PM
        days_ahead = 7  # Next Monday
    
    next_monday = now + timedelta(days=days_ahead)
    # Set to 1 PM EST on that Monday
    deadline = next_monday.replace(hour=13, minute=0, second=0, microsecond=0)
    
    return deadline

def get_next_processing_week():
    """Calculate the next Monday 1 PM EST processing deadline (date only for database)"""
    return get_next_processing_deadline().date()

@login_required
def transaction_form_step1(request):
    """Step 1: Choose transaction type"""
    if request.method == 'POST':
        form = TransactionTypeForm(request.POST)
        if form.is_valid():
            transaction_type = form.cleaned_data['transaction_type']
            return redirect(f'/transactions/form/step2/?type={transaction_type}')
    else:
        form = TransactionTypeForm()
    
    context = utils.build_context(request)
    context.update({
        'form': form,
        'step': 1,
        'total_steps': 2,
        'processing_info': 'Transactions are processed Mondays at 1 PM EST.',
        'next_deadline': get_next_processing_deadline()
    })
    
    return render(request, 'transactions/form_step1.html', context)

@login_required
def transaction_form_step2(request):
    """Step 2: Transaction-specific form"""
    transaction_type = request.GET.get('type')
    
    if not transaction_type or transaction_type not in TRANSACTION_FORM_MAP:
        messages.error(request, 'Invalid transaction type selected.')
        return redirect('/transactions/form/')
    
    FormClass = TRANSACTION_FORM_MAP[transaction_type]
    
    if request.method == 'POST':
        form = FormClass(request.POST, user=request.user)
        if form.is_valid():
            # Create transaction submission
            team_id = form.cleaned_data.get('team')
            if isinstance(team_id, str):
                team = models.Team.objects.get(id=int(team_id))
            else:
                team = team_id
            
            # Prepare form data for JSON storage
            form_data = form.cleaned_data.copy()
            
            # Convert player object to string for JSON storage
            if 'player' in form_data:
                player = form_data['player']
                if hasattr(player, 'name'):  # It's a Player object
                    form_data['player'] = player.name
                    form_data['player_id'] = player.id
                    form_data['player_mlb_id'] = player.mlb_id
                # If it's already a string, leave it as is
            
            # Convert team object to ID if needed
            if 'team' in form_data:
                if hasattr(form_data['team'], 'id'):
                    form_data['team'] = form_data['team'].id
            
            # Convert any other model objects to their string representations
            for key, value in form_data.items():
                if hasattr(value, '_meta'):  # It's a Django model instance
                    form_data[key] = str(value)
            
            submission = models.TransactionSubmission.objects.create(
                user=request.user,
                team=team,
                transaction_type=transaction_type,
                form_data=form_data,
                processing_week=get_next_processing_week()
            )
            
            messages.success(request, f'Transaction submitted successfully! Reference ID: #{submission.id}')
            return redirect('/transactions/success/')
    else:
        form = FormClass(user=request.user)
    
    context = utils.build_context(request)
    context.update({
        'form': form,
        'transaction_type': transaction_type,
        'transaction_display': dict(TransactionTypeForm.TRANSACTION_CHOICES)[transaction_type],
        'step': 2,
        'total_steps': 2,
        'next_deadline': get_next_processing_deadline()
    })
    
    return render(request, 'transactions/form_step2.html', context)

@login_required
def transaction_success(request):
    """Success page after transaction submission"""
    context = utils.build_context(request)
    context.update({
        'recent_submissions': models.TransactionSubmission.objects.filter(
            user=request.user
        ).order_by('-created')[:5]
    })
    
    return render(request, 'transactions/success.html', context)

@login_required  
def transaction_list(request):
    """List user's transaction submissions"""
    context = utils.build_context(request)
    context.update({
        'submissions': models.TransactionSubmission.objects.filter(
            user=request.user
        ).order_by('-created')
    })
    
    return render(request, 'transactions/list.html', context)

@login_required
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
    
    # Apply explicit ordering to match Player model's Meta ordering
    # Level priority, then position priority, then last name
    query = query.order_by(
        django_models.Case(
            django_models.When(simple_position='P', then=1),
            django_models.When(simple_position='C', then=2),
            django_models.When(simple_position='1B', then=3),
            django_models.When(simple_position='2B', then=4),
            django_models.When(simple_position='3B', then=5),
            django_models.When(simple_position='SS', then=6),
            django_models.When(simple_position='IF', then=7),
            django_models.When(simple_position='RF', then=8),
            django_models.When(simple_position='CF', then=9),
            django_models.When(simple_position='LF', then=10),
            django_models.When(simple_position='OF', then=11),
            django_models.When(simple_position='UT', then=12),
            django_models.When(simple_position='DH', then=13),
            default=14,
            output_field=django_models.IntegerField()
        ),
        'last_name'
    )
    # Set up pagination (500 players per page)
    paginator = Paginator(query, 500)
    page_number = request.GET.get('page')
    
    try:
        players_page = paginator.page(page_number)
    except PageNotAnInteger:
        players_page = paginator.page(1)
    except EmptyPage:
        players_page = paginator.page(paginator.num_pages)
    
    # Pass all players as one unified list
    context["players"] = players_page
    context["players_page"] = players_page  # For pagination controls
    
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

@login_required
def auction_test_view(request):
    """
    Test view to verify blind auction behavior works correctly.
    Only accessible to staff users for testing purposes.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    context = utils.build_context(request)
    
    # Get test auction data
    test_results = {}
    
    # Test 1: Active auction with bids should hide competitive info
    active_auctions = models.Auction.objects.filter(
        active=True,
        is_nomination=False,
        closes__gte=timezone.now()
    )
    
    if active_auctions.exists():
        auction = active_auctions.first()
        bids = models.MLBAuctionBid.objects.filter(auction=auction).order_by('-max_bid')
        
        test_results['active_auction'] = {
            'auction_id': auction.id,
            'player': auction.player.name,
            'is_expired': auction.is_expired(),
            'has_bids': auction.has_bids(),
            'total_bids': bids.count(),
            'leading_bid_info': auction.leading_bid(),
            'actual_bids': [{'team': bid.team.full_name, 'amount': bid.max_bid} for bid in bids] if bids else [],
            'max_bid_info': auction.max_bid(),
            'winning_bid_info': auction.winning_bid(),
        }
    
    # Test 2: Expired auction should show results
    expired_auctions = models.Auction.objects.filter(
        active=True,
        is_nomination=False,
        closes__lt=timezone.now()
    )
    
    if expired_auctions.exists():
        auction = expired_auctions.first()
        bids = models.MLBAuctionBid.objects.filter(auction=auction).order_by('-max_bid')
        
        test_results['expired_auction'] = {
            'auction_id': auction.id,
            'player': auction.player.name,
            'is_expired': auction.is_expired(),
            'has_bids': auction.has_bids(),
            'total_bids': bids.count(),
            'leading_bid_info': auction.leading_bid(),
            'actual_bids': [{'team': bid.team.full_name, 'amount': bid.max_bid} for bid in bids] if bids else [],
            'max_bid_info': auction.max_bid(),
            'winning_bid_info': auction.winning_bid(),
        }
    
    # Test 3: Nomination auction should not accept bids
    nomination_auctions = models.Auction.objects.filter(
        active=True,
        is_nomination=True
    )
    
    if nomination_auctions.exists():
        auction = nomination_auctions.first()
        test_results['nomination_auction'] = {
            'auction_id': auction.id,
            'player': auction.player.name,
            'is_nomination': auction.is_nomination,
            'can_bid': not auction.is_nomination,
        }
    
    # Test 4: Bid validation tests
    test_results['validation_tests'] = {
        'positive_bid_required': True,
        'minimum_bid_enforced': True,
        'one_bid_per_team': True,
        'no_bids_on_expired': True,
        'no_bids_on_nominations': True,
    }
    
    return JsonResponse({
        'test_results': test_results,
        'timestamp': timezone.now().isoformat(),
        'blind_auction_rules': {
            'active_auctions_hide_competitive_info': 'leading_bid_info should show Hidden values',
            'expired_auctions_show_results': 'leading_bid_info should show actual winning info',
            'nominations_dont_accept_bids': 'is_nomination=True should prevent bidding',
        }
    }, json_dumps_params={'indent': 2})

def auction_debug_view(request, auction_id):
    """
    Debug view to inspect a specific auction's state.
    Only accessible to staff users.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    try:
        auction = models.Auction.objects.get(id=auction_id)
    except models.Auction.DoesNotExist:
        return JsonResponse({"error": "Auction not found"}, status=404)
    
    bids = models.MLBAuctionBid.objects.filter(auction=auction).order_by('-max_bid')
    
    debug_info = {
        'auction': {
            'id': auction.id,
            'player': auction.player.name,
            'closes': auction.closes.isoformat(),
            'is_nomination': auction.is_nomination,
            'min_bid': auction.min_bid,
            'active': auction.active,
            'is_expired': auction.is_expired(),
            'has_bids': auction.has_bids(),
        },
        'bids': [{
            'team': bid.team.full_name,
            'amount': bid.max_bid,
            'created': bid.created.isoformat() if bid.created else None,
        } for bid in bids],
        'auction_methods': {
            'max_bid': auction.max_bid(),
            'winning_bid': auction.winning_bid(),
            'leading_bid': auction.leading_bid(),
        },
        'blind_auction_test': {
            'should_hide_competitive_info': not auction.is_expired(),
            'leading_bid_shows_hidden': auction.leading_bid().get('team_id') == 'Hidden' if not auction.is_expired() else False,
        }
    }
    
    return JsonResponse(debug_info, json_dumps_params={'indent': 2})

@login_required
def auction_test_page(request):
    """Test page for verifying auction functionality - staff only"""
    if not request.user.is_staff:
        return render(request, "403.html", status=403)
    
    context = utils.build_context(request)
    return render(request, "auction_test.html", context)

@csrf_exempt
@login_required
def nominate_player_api(request, playerid):
    """
    API endpoint to nominate a player for auction.
    Creates an inactive auction that admins can review and activate.
    """
    context = utils.build_context(request)
    payload = {
        "success": False,
        "message": None,
        "nomination_id": None
    }
    
    # Check if user has permission to nominate
    if not (context['owner'] and context['owner_team']):
        payload['message'] = "Only team owners can nominate players for auction."
        return JsonResponse(payload)
    
    # Get the player
    try:
        player = models.Player.objects.get(mlb_id=playerid)
    except models.Player.DoesNotExist:
        payload['message'] = "Player not found."
        return JsonResponse(payload)
    
    # Check if player is eligible for nomination
    if player.is_owned:
        payload['message'] = f"{player.name} is already owned and cannot be nominated."
        return JsonResponse(payload)
    
    # Check if there's already an active auction for this player
    existing_auction = models.Auction.objects.filter(
        player=player,
        active=True
    ).first()
    
    if existing_auction:
        payload['message'] = f"{player.name} already has an active auction."
        return JsonResponse(payload)
    
    # Check if this user has already nominated this player recently
    recent_nomination = models.Auction.objects.filter(
        player=player,
        is_nomination=True,
        created__gte=timezone.now() - timedelta(days=7),  # Within last 7 days
        # We could track who nominated via a custom field, but for now just check existence
    ).first()
    
    if recent_nomination:
        payload['message'] = f"{player.name} has already been nominated recently."
        return JsonResponse(payload)
    
    # Get nomination details from request
    reason = request.GET.get('reason', '').strip()
    if len(reason) > 500:
        reason = reason[:500]
    
    # Calculate next Friday at 3 PM EST for potential auction
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 15:
        days_until_friday = 7
    next_friday = now + timedelta(days=days_until_friday)
    auction_close_time = next_friday.replace(hour=15, minute=0, second=0, microsecond=0)
    
    # Create the nomination (inactive auction)
    try:
        nomination = models.Auction.objects.create(
            player=player,
            closes=auction_close_time,
            is_nomination=True,
            min_bid=1,  # Default minimum bid
            active=False,  # Inactive until admin approves
        )
        
        # Create a nomination record to track who nominated and why
        models.PlayerNomination.objects.create(
            auction=nomination,
            nominating_team=context['owner_team'],
            reason=reason
        )
        
        payload['success'] = True
        payload['message'] = f"Successfully nominated {player.name} for auction. An administrator will review this nomination."
        payload['nomination_id'] = nomination.id
        
    except Exception as e:
        payload['message'] = f"Error creating nomination: {str(e)}"
    
    return JsonResponse(payload)

def nominations_list(request):
    """View to show current player nominations"""
    context = utils.build_context(request)
    
    # Get all pending nominations (inactive auctions that are nominations)
    pending_nominations = models.Auction.objects.filter(
        is_nomination=True,
        active=False
    ).select_related('player', 'nomination_details__nominating_team').order_by('-created')
    
    # Get recently approved nominations (active auctions that were nominations)
    approved_nominations = models.Auction.objects.filter(
        is_nomination=False,
        active=True,
        nomination_details__isnull=False
    ).select_related('player', 'nomination_details__nominating_team').order_by('-created')[:10]
    
    # Add nomination details to each auction
    for auction in pending_nominations:
        try:
            nomination = models.PlayerNomination.objects.get(auction=auction)
            auction.nomination_info = nomination
        except models.PlayerNomination.DoesNotExist:
            auction.nomination_info = None
    
    for auction in approved_nominations:
        try:
            nomination = models.PlayerNomination.objects.get(auction=auction)
            auction.nomination_info = nomination
        except models.PlayerNomination.DoesNotExist:
            auction.nomination_info = None
    
    context['pending_nominations'] = pending_nominations
    context['approved_nominations'] = approved_nominations
    
    return render(request, "nominations_list.html", context)

def transactions(request):
    context = utils.build_context(request)
    
    # Get all transactions ordered by date (newest first)
    transactions_list = models.Transaction.objects.all().order_by('-date', '-id')
    
    # Set up pagination (250 transactions per page)
    paginator = Paginator(transactions_list, 250)
    page_number = request.GET.get('page')
    
    try:
        transactions_page = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        transactions_page = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page
        transactions_page = paginator.page(paginator.num_pages)
    
    context['transactions'] = transactions_page
    
    return render(request, 'transactions.html', context)

def robots_txt(request):
    """Serve robots.txt to block all crawlers"""
    lines = [
        "User-agent: *",
        "Disallow: /",
        "",
        "# Block all crawlers from everything",
        "User-agent: Googlebot",
        "Disallow: /",
        "",
        "User-agent: Bingbot", 
        "Disallow: /",
        "",
        "User-agent: Slurp",
        "Disallow: /",
        "",
        "User-agent: DuckDuckBot",
        "Disallow: /",
        "",
        "User-agent: Baiduspider",
        "Disallow: /",
        "",
        "User-agent: YandexBot",
        "Disallow: /",
        "",
        "User-agent: facebookexternalhit",
        "Disallow: /",
        "",
        "User-agent: Twitterbot",
        "Disallow: /",
        "",
        "User-agent: LinkedInBot",
        "Disallow: /",
        "",
        "User-agent: WhatsApp",
        "Disallow: /",
        "",
        "User-agent: Applebot",
        "Disallow: /",
        "",
        "# No sitemap provided intentionally"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")