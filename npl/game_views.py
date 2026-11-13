"""Weekly schedule, the computer's instructions, box scores, and player cards."""

from django.contrib import messages
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from npl import models, utils
from npl.computer_manager import (
    BULLPEN_CHOICES,
    BUNT_CHOICES,
    DEFENSE_SITUATIONS,
    HOOK_CHOICES,
    HIT_AND_RUN_CHOICES,
    PH_SITUATIONS,
    RUN_SITUATIONS,
    STEAL_CHOICES,
    describe_bullpen_logic,
)
from npl.weekly_plan import (
    BULLPEN_SLOTS,
    DEFENSE_ROWS,
    LINEUP_POSITIONS,
    PH_ROWS,
    RUN_ROWS,
    PlanError,
    active_roster,
    bullpen_ids,
    ensure_plan,
    focus_week,
    is_pitcher,
    lineup_rows,
    opponent,
    parse_bench,
    parse_bullpen,
    parse_lineup,
    parse_rotation,
    plan_is_open,
    player_label,
    previous_plan,
    rotation_ids,
    save_bench,
    save_bullpen,
    save_lineup,
    save_rotation,
    series_for,
    series_played,
    user_owns,
)


def schedule(request, year=None):
    context = utils.build_context(request)
    season = _season(year)
    context["season"] = season
    context["year"] = season.year if season else year
    weeks = []
    if season is not None:
        series = (
            models.WeekSeries.objects.filter(week__season=season)
            .select_related("week", "home_team", "road_team")
            .order_by("week__number", "home_team__abbreviation")
        )
        grouped = {}
        for item in series:
            grouped.setdefault(item.week_id, {"week": item.week, "series": []})
            grouped[item.week_id]["series"].append(item)
        weeks = [grouped[key] for key in sorted(grouped, key=lambda week_id: grouped[week_id]["week"].number)]
    context["weeks"] = weeks
    context["today"] = timezone.localdate()
    context["owner_team_id"] = context["owner_team"].id if context.get("owner_team") else None
    return render(request, "schedule.html", context)


def series_detail(request, series_id):
    context = utils.build_context(request)
    series = get_object_or_404(
        models.WeekSeries.objects.select_related("week", "week__season", "home_team", "road_team"),
        pk=series_id,
    )
    context["series"] = series
    context["games"] = list(series.results.order_by("number"))
    context["sides"] = [
        _public_side(request, series, series.home_team),
        _public_side(request, series, series.road_team),
    ]
    return render(request, "series.html", context)


def week_game(request, game_id):
    context = utils.build_context(request)
    game = get_object_or_404(
        models.WeekGame.objects.select_related(
            "series", "series__week", "series__week__season", "series__home_team", "series__road_team"
        ),
        pk=game_id,
    )
    context["game"] = game
    context["series"] = game.series
    context["box"] = game.box_score or {}
    return render(request, "box_score.html", context)


def lineup(request, short_name, year=None, week=None):
    return _instruction(request, short_name, year, week, "lineup")


def rotation(request, short_name, year=None, week=None):
    return _instruction(request, short_name, year, week, "rotation")


def bullpen(request, short_name, year=None, week=None):
    return _instruction(request, short_name, year, week, "bullpen")


def bench(request, short_name, year=None, week=None):
    return _instruction(request, short_name, year, week, "bench")


def team_cards(request, short_name, year=None, week=None):
    context = utils.build_context(request)
    team = _team(short_name)
    season, week_number = _card_target(year, week)
    context.update({"team": team, "season": season, "week_number": week_number, "viewer_owns": user_owns(request.user, team)})
    if season is None:
        context["rows"] = []
        return render(request, "team_cards.html", context)
    cards = {
        card.player_id: card
        for card in models.PlayerWeekCard.objects.filter(season=season, week=week_number, player__team=team)
    }
    rows = []
    for player in active_roster(team):
        card = cards.get(player.mlb_id)
        rows.append({"player": player, "card": card, "lines": _card_lines(card)})
    context["rows"] = rows
    context["weeks"] = list(range(1, 28))
    return render(request, "team_cards.html", context)


def player_cards(request, playerid):
    context = utils.build_context(request)
    player = get_object_or_404(models.Player.objects.select_related("team"), mlb_id=playerid)
    cards = list(
        models.PlayerWeekCard.objects.filter(player=player).select_related("season").order_by("season__year", "week")
    )
    context["player"] = player
    context["cards"] = [{"card": card, "lines": _card_lines(card)} for card in cards]
    return render(request, "player_cards.html", context)


def _instruction(request, short_name, year, week, section):
    context = utils.build_context(request)
    team = _team(short_name)
    season = _season(year)
    context.update(_shell(team, season, request))
    if season is None:
        return render(request, "week_unscheduled.html", context)

    week_number = week
    if week_number is None:
        chosen = focus_week(season, timezone.localdate())
        if chosen is None:
            return render(request, "week_unscheduled.html", context)
        return redirect(_section_url(section, team, season.year, chosen.number))

    series = series_for(team, season, week_number)
    if series is None:
        raise Http404("That week is not on the schedule.")
    context.update(_series_context(request, team, series, section))
    roster = context["roster"]
    players = {player.mlb_id: player for player in roster}

    if request.method == "POST":
        if not context["can_edit"]:
            return HttpResponseForbidden("This card is locked.")
        errors = _save_section(section, request, team, series, roster, players)
        if errors:
            context["errors"] = errors
            context.update(_posted_draft(section, request.POST, context))
            return render(request, _template(section), context)
        messages.success(request, f"Week {series.week.number} {section} saved.")
        return redirect(_section_url(section, team, season.year, series.week.number))

    if context["can_view"]:
        context.update(_saved_draft(section, context["plan"], context["carried_plan"]))
    return render(request, _template(section), context)


def _save_section(section, request, team, series, roster, players):
    plan = ensure_plan(team, series)
    try:
        if section == "lineup":
            parsed, errors = parse_lineup(request.POST, players)
            if errors:
                return errors
            save_lineup(plan, parsed, roster)
        elif section == "rotation":
            slots, errors = parse_rotation(request.POST, players)
            if errors:
                return errors
            save_rotation(plan, slots)
        elif section == "bullpen":
            parsed, errors = parse_bullpen(request.POST, players)
            if errors:
                return errors
            save_bullpen(plan, parsed)
        else:
            parsed, errors = parse_bench(request.POST, players)
            if errors:
                return errors
            save_bench(plan, parsed)
    except PlanError as error:
        return error.errors
    return []


def _shell(team, season, request):
    return {
        "team": team,
        "season": season,
        "year": season.year if season else None,
        "viewer_owns": user_owns(request.user, team),
    }


def _series_context(request, team, series, section):
    played = series_played(series)
    owns = user_owns(request.user, team)
    staff = request.user.is_staff
    can_edit = (owns or staff) and plan_is_open(series.week, timezone.localdate(), played, staff)
    can_view = owns or staff or not plan_is_open(series.week, timezone.localdate(), played, False)
    other, at_home = opponent(series, team)
    plan = models.WeeklyPlan.objects.filter(team=team, series=series).first()
    carried = previous_plan(team, series)
    roster = active_roster(team)
    hitters = [player for player in roster if not is_pitcher(player)]
    pitchers = [player for player in roster if is_pitcher(player)]
    return {
        "series": series,
        "week": series.week,
        "section": section,
        "opponent": other,
        "at_home": at_home,
        "played": played,
        "can_edit": can_edit,
        "can_view": can_view,
        "plan": plan,
        "carried_plan": carried,
        "roster": roster,
        "hitters": [(player.mlb_id, player_label(player)) for player in hitters],
        "pitchers": [(player.mlb_id, player_label(player)) for player in pitchers],
        "positions": LINEUP_POSITIONS,
        "usages": [(value, label, describe_bullpen_logic(value)) for value, label in BULLPEN_CHOICES],
        "hooks": HOOK_CHOICES,
        "steals": STEAL_CHOICES,
        "bunts": BUNT_CHOICES,
        "hit_and_runs": HIT_AND_RUN_CHOICES,
        "ph_situations": PH_SITUATIONS,
        "defense_situations": DEFENSE_SITUATIONS,
        "run_situations": RUN_SITUATIONS,
        "bullpen_slots": BULLPEN_SLOTS,
        "ph_rows": range(1, PH_ROWS + 1),
        "defense_rows": range(1, DEFENSE_ROWS + 1),
        "run_rows": range(1, RUN_ROWS + 1),
        "errors": [],
    }


def _saved_draft(section, plan, carried):
    source = plan
    carried_over = False
    flag = {"lineup": "lineup_saved", "rotation": "rotation_saved", "bullpen": "bullpen_saved", "bench": "bench_saved"}[
        section
    ]
    filed = plan is not None and getattr(plan, flag)
    if not filed and carried is not None and getattr(carried, flag):
        source = carried
        carried_over = True
    draft = {"carried_over": carried_over and source is not None}
    if section == "lineup":
        draft["right_rows"] = lineup_rows(source, "R")
        draft["left_rows"] = lineup_rows(source, "L")
    elif section == "rotation":
        draft["starters"] = rotation_ids(source)
    elif section == "bullpen":
        draft["usage"] = source.usage if source else "traditional"
        draft["hook"] = source.hook if source else "normal"
        draft["groups"] = bullpen_ids(source)
    else:
        draft.update(_bench_draft(source))
    return draft


def _posted_draft(section, post, context):
    draft = {"carried_over": False}
    if section == "lineup":
        draft["right_rows"] = _posted_line(post, "r")
        draft["left_rows"] = _posted_line(post, "l")
    elif section == "rotation":
        draft["starters"] = [post.get(f"starter_{number}", "") for number in range(1, 7)]
    elif section == "bullpen":
        draft["usage"] = post.get("usage") or "traditional"
        draft["hook"] = post.get("hook") or "normal"
        draft["groups"] = {
            role: [post.get(f"{role}_{order}", "") for order in range(1, count + 1)]
            for role, count in BULLPEN_SLOTS
        }
    else:
        draft.update(_posted_bench(post))
    return draft


def _posted_line(post, prefix):
    return [
        {
            "order": order,
            "player_id": post.get(f"{prefix}_player_{order}", ""),
            "position": post.get(f"{prefix}_pos_{order}", ""),
        }
        for order in range(1, 10)
    ]


def _bench_draft(plan):
    blank_hit = [
        {"player_id": "", "for_id": "", "inning": 7, "situation": "tied_or_trailing"} for _ in range(PH_ROWS)
    ]
    draft = {
        "steal": "normal",
        "bunt": "never",
        "hit_and_run": "never",
        "ph_r": [dict(row) for row in blank_hit],
        "ph_l": [dict(row) for row in blank_hit],
        "defense": [
            {"out_id": "", "in_id": "", "inning": 8, "situation": "leading"} for _ in range(DEFENSE_ROWS)
        ],
        "runs": [{"player_id": "", "for_id": "", "inning": 7, "situation": "close"} for _ in range(RUN_ROWS)],
    }
    if plan is None:
        return draft
    draft["steal"] = plan.steal
    draft["bunt"] = plan.bunt
    draft["hit_and_run"] = plan.hit_and_run
    for rule in plan.pinch_hits.all():
        bucket = draft["ph_r"] if rule.vs_hand == "R" else draft["ph_l"]
        if 1 <= rule.order <= PH_ROWS:
            bucket[rule.order - 1] = {
                "player_id": rule.player_id,
                "for_id": rule.for_player_id or "",
                "inning": rule.earliest_inning,
                "situation": rule.situation,
            }
    for rule in plan.defense_subs.all():
        if 1 <= rule.order <= DEFENSE_ROWS:
            draft["defense"][rule.order - 1] = {
                "out_id": rule.out_player_id,
                "in_id": rule.in_player_id,
                "inning": rule.earliest_inning,
                "situation": rule.situation,
            }
    for rule in plan.pinch_runs.all():
        if 1 <= rule.order <= RUN_ROWS:
            draft["runs"][rule.order - 1] = {
                "player_id": rule.player_id,
                "for_id": rule.for_player_id or "",
                "inning": rule.earliest_inning,
                "situation": rule.situation,
            }
    return draft


def _posted_bench(post):
    def hits(prefix):
        return [
            {
                "player_id": post.get(f"{prefix}_{order}", ""),
                "for_id": post.get(f"{prefix}_for_{order}", ""),
                "inning": post.get(f"{prefix}_inning_{order}", "7"),
                "situation": post.get(f"{prefix}_when_{order}", "tied_or_trailing"),
            }
            for order in range(1, PH_ROWS + 1)
        ]

    return {
        "steal": post.get("steal") or "normal",
        "bunt": post.get("bunt") or "never",
        "hit_and_run": post.get("hit_and_run") or "never",
        "ph_r": hits("ph_r"),
        "ph_l": hits("ph_l"),
        "defense": [
            {
                "out_id": post.get(f"def_out_{order}", ""),
                "in_id": post.get(f"def_in_{order}", ""),
                "inning": post.get(f"def_inning_{order}", "8"),
                "situation": post.get(f"def_when_{order}", "leading"),
            }
            for order in range(1, DEFENSE_ROWS + 1)
        ],
        "runs": [
            {
                "player_id": post.get(f"pr_{order}", ""),
                "for_id": post.get(f"pr_for_{order}", ""),
                "inning": post.get(f"pr_inning_{order}", "7"),
                "situation": post.get(f"pr_when_{order}", "close"),
            }
            for order in range(1, RUN_ROWS + 1)
        ],
    }


def _public_side(request, series, team):
    """A club's filed card, hidden until the Monday deadline from everyone but that club."""
    owns = user_owns(request.user, team)
    locked = timezone.localdate() > series.week.lineup_due or series_played(series)
    visible = owns or request.user.is_staff or locked
    plan = models.WeeklyPlan.objects.filter(team=team, series=series).prefetch_related(
        "lineup_slots__player", "rotation_slots__player", "bullpen_slots__player"
    ).first()
    filed = plan is not None and plan.lineup_slots.exists()
    return {"team": team, "visible": visible, "plan": plan if visible else None, "filed": filed}


def _card_lines(card):
    if card is None:
        return None
    talent = card.true_talent or {}
    usage = card.week_usage or {}
    return {
        "summary": talent.get("summary") or "",
        "prior_percent": talent.get("prior_percent"),
        "hitting": _side_line(talent.get("hitting"), usage.get("hitting"), usage.get("hitting_known"), "hit"),
        "pitching": _side_line(talent.get("pitching"), usage.get("pitching"), usage.get("pitching_known"), "pitch"),
    }


def _side_line(block, week, known, kind):
    if not block or not block.get("talent"):
        return None
    talent = block["talent"]
    if kind == "hit":
        measure = (
            f"K {talent['k_pct']}% · BB {talent['bb_pct']}% · "
            f"BABIP {talent['babip']} · HR/PA {round((talent['hr_pa'] or 0) * 100, 1)}%"
        )
        if not known:
            played = "This week's plate appearances are not split out yet."
        elif not week or week.get("pa", 0) <= 0:
            played = "No plate appearances this week."
        else:
            played = f"{_whole(week.get('pa'))} PA · {_whole(week.get('hr'))} HR · {_whole(week.get('k'))} K · {_whole(week.get('bb'))} BB"
    else:
        measure = f"K/9 {talent['k_9']} · BB/9 {talent['bb_9']} · HR/9 {talent['hr_9']} · FIP {talent['fip']}"
        if not known:
            played = "This week's innings are not split out yet."
        elif not week or week.get("ip", 0) <= 0:
            played = "No innings this week."
        else:
            played = f"{week.get('ip')} IP · {_whole(week.get('k'))} K · {_whole(week.get('bb'))} BB · {_whole(week.get('hr'))} HR"
    prior = block.get("prior")
    return {"measure": measure, "usage": played, "prior": prior}


def _whole(value):
    return int(round(float(value or 0)))


def _team(short_name):
    return get_object_or_404(models.Team.objects.select_related("league", "division"), short_name__iexact=short_name)


def _season(year):
    if year is None:
        return models.Season.current()
    return models.Season.objects.filter(year=year).order_by("-is_current", "-id").first()


def _card_target(year, week):
    season = _season(year)
    if week is not None:
        return season, week
    if season is None:
        return None, 1
    chosen = focus_week(season, timezone.localdate())
    if chosen is not None:
        return season, chosen.number
    return season, 1


def _template(section):
    return {
        "lineup": "team_lineup.html",
        "rotation": "team_rotation.html",
        "bullpen": "team_bullpen.html",
        "bench": "team_bench.html",
    }[section]


def _section_url(section, team, year, week):
    name = {"lineup": "team_lineup_week", "rotation": "team_rotation_week", "bullpen": "team_bullpen_week", "bench": "team_bench_week"}[
        section
    ]
    return reverse(name, args=[team.short_name.lower(), year, week])
