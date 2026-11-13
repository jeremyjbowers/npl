"""Read and write the weekly instructions the computer manager plays from."""

from django.db import transaction
from django.utils import timezone

from npl import models
from npl.computer_manager import (
    BULLPEN_CHOICES,
    BUNT_CHOICES,
    DEFENSE_SITUATIONS,
    HOOK_CHOICES,
    HIT_AND_RUN_CHOICES,
    PH_SITUATIONS,
    RUN_SITUATIONS,
    STEAL_CHOICES,
    DefenseMove,
    PinchHit,
    PinchRun,
    Script,
)
from npl.rosters import is_active_mlb, position_bucket


LINEUP_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
BULLPEN_SLOTS = (
    ("closer", 1),
    ("sirp", 4),
    ("mirp", 3),
    ("mopup", 2),
    ("lefty", 2),
    ("righty", 2),
)
PH_ROWS = 4
DEFENSE_ROWS = 3
RUN_ROWS = 2

USAGE_VALUES = {value for value, _label in BULLPEN_CHOICES}
HOOK_VALUES = {value for value, _label in HOOK_CHOICES}
STEAL_VALUES = {value for value, _label in STEAL_CHOICES}
BUNT_VALUES = {value for value, _label in BUNT_CHOICES}
HIT_VALUES = {value for value, _label in HIT_AND_RUN_CHOICES}
PH_VALUES = {value for value, _label in PH_SITUATIONS}
DEFENSE_VALUES = {value for value, _label in DEFENSE_SITUATIONS}
RUN_VALUES = {value for value, _label in RUN_SITUATIONS}


class PlanError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def active_roster(team):
    players = models.Player.objects.filter(team=team).defer(
        "stats", "scoresheet_defense", "scoresheet_offense"
    )
    return [player for player in players if is_active_mlb(player)]


def is_pitcher(player):
    return position_bucket(player.simple_position or player.position) == "P"


def is_catcher(player):
    return position_bucket(player.simple_position or player.position) == "C"


def player_label(player):
    bucket = position_bucket(player.simple_position or player.position)
    hand = ""
    if bucket == "P" and player.throws:
        hand = f" {player.throws}"
    elif player.bats:
        hand = f" {player.bats}"
    spot = player.simple_position or player.position or ""
    return f"{player.last_name}, {player.first_name} ({spot}{hand})"


def user_owns(user, team):
    if not user.is_authenticated:
        return False
    return team.owners.filter(user_id=user.id).exists()


def series_played(series):
    return series.results.filter(home_score__isnull=False, road_score__isnull=False).exists()


def plan_is_open(week, today, played, staff):
    if played:
        return False
    if staff:
        return True
    return today <= week.lineup_due


def focus_week(season, today):
    weeks = list(season.schedule_weeks.order_by("number"))
    for week in weeks:
        if today <= week.lineup_due:
            return week
    return weeks[-1] if weeks else None


def series_for(team, season, week_number):
    return (
        models.WeekSeries.objects.filter(week__season=season, week__number=week_number)
        .filter(models_q_team(team))
        .select_related("week", "week__season", "home_team", "road_team")
        .first()
    )


def models_q_team(team):
    from django.db.models import Q

    return Q(home_team=team) | Q(road_team=team)


def opponent(series, team):
    if series.home_team_id == team.id:
        return series.road_team, True
    return series.home_team, False


def ensure_plan(team, series):
    plan, _created = models.WeeklyPlan.objects.get_or_create(team=team, series=series)
    return plan


def previous_plan(team, series):
    return (
        models.WeeklyPlan.objects.filter(team=team, series__week__season=series.week.season)
        .filter(series__week__number__lt=series.week.number)
        .order_by("-series__week__number")
        .first()
    )


def _by_id(players):
    return {player.mlb_id: player for player in players}


def _posted_player(post, name, players):
    raw = (post.get(name) or "").strip()
    if not raw:
        return None, None
    player = players.get(raw)
    if player is None:
        return None, f"{raw} is not on the active roster."
    return player, None


def _inning(post, name, default):
    raw = (post.get(name) or "").strip()
    if raw == "":
        return default, None
    if not raw.isdigit() or not 1 <= int(raw) <= 12:
        return default, "Innings run from 1 to 12."
    return int(raw), None


def validate_lineup(slots, roster, label):
    """``slots`` is a list of nine (player, position) pairs, or fewer when a spot was left blank."""
    errors = []
    if len(slots) != 9:
        errors.append(f"The {label} lineup needs nine batters.")
        return errors
    catchers = {player.mlb_id for player in roster if is_catcher(player)}
    seen = []
    positions = []
    for player, position in slots:
        if player is None:
            errors.append(f"The {label} lineup has an empty spot.")
            continue
        if is_pitcher(player):
            errors.append(f"{player_label(player)} is a pitcher and cannot hit.")
        if position not in LINEUP_POSITIONS:
            errors.append(f"{position or 'A blank position'} is not a lineup position.")
        seen.append(player.mlb_id)
        positions.append(position)
    if len(set(seen)) != len(seen):
        errors.append(f"The {label} lineup uses a batter twice.")
    if len([pos for pos in positions if pos]) != len(set(positions)):
        errors.append(f"The {label} lineup files a position twice.")
    if positions and set(positions) != set(LINEUP_POSITIONS):
        errors.append(f"The {label} lineup needs one of each position, including the designated hitter.")
    catcher_slots = [player for player, position in slots if position == "C" and player is not None]
    if catchers and (not catcher_slots or catcher_slots[0].mlb_id not in catchers):
        errors.append(f"The {label} lineup has to catch a catcher.")
    return errors


def parse_lineup(post, players):
    errors = []
    parsed = {"R": [], "L": []}
    for hand, prefix in (("R", "r"), ("L", "l")):
        for order in range(1, 10):
            player, problem = _posted_player(post, f"{prefix}_player_{order}", players)
            if problem:
                errors.append(problem)
            position = (post.get(f"{prefix}_pos_{order}") or "").strip()
            parsed[hand].append((player, position, order))
    return parsed, errors


def parse_rotation(post, players):
    errors = []
    slots = []
    for number in range(1, 7):
        player, problem = _posted_player(post, f"starter_{number}", players)
        if problem:
            errors.append(problem)
        if player is None:
            errors.append(f"Game {number} needs a starter.")
        elif not is_pitcher(player):
            errors.append(f"{player_label(player)} does not pitch.")
        slots.append(player)
    return slots, errors


def parse_bullpen(post, players):
    errors = []
    usage = post.get("usage") or "traditional"
    hook = post.get("hook") or "normal"
    if usage not in USAGE_VALUES:
        errors.append("Pick a bullpen usage.")
    if hook not in HOOK_VALUES:
        errors.append("Pick a starter hook.")
    grouped = {role: [] for role, _count in BULLPEN_SLOTS}
    seen = []
    for role, count in BULLPEN_SLOTS:
        for order in range(1, count + 1):
            player, problem = _posted_player(post, f"{role}_{order}", players)
            if problem:
                errors.append(problem)
            if player is None:
                continue
            if not is_pitcher(player):
                errors.append(f"{player_label(player)} does not pitch.")
            grouped[role].append(player)
            seen.append(player.mlb_id)
    if len(set(seen)) != len(seen):
        errors.append("A pitcher is listed twice in the bullpen.")
    if usage == "traditional" and not grouped["closer"]:
        errors.append("Traditional usage needs a closer.")
    if not seen:
        errors.append("Name at least one reliever.")
    return {"usage": usage, "hook": hook, "groups": grouped}, errors


def _choice(post, name, allowed, label, default):
    value = post.get(name) or default
    if value not in allowed:
        return default, f"Pick a {label}."
    return value, None


def parse_bench(post, players):
    errors = []
    steal, problem = _choice(post, "steal", STEAL_VALUES, "steal setting", "normal")
    if problem:
        errors.append(problem)
    bunt, problem = _choice(post, "bunt", BUNT_VALUES, "bunt setting", "never")
    if problem:
        errors.append(problem)
    hit_and_run, problem = _choice(post, "hit_and_run", HIT_VALUES, "hit-and-run setting", "never")
    if problem:
        errors.append(problem)

    pinch_hits = []
    for hand, prefix in (("R", "ph_r"), ("L", "ph_l")):
        for order in range(1, PH_ROWS + 1):
            player, problem = _posted_player(post, f"{prefix}_{order}", players)
            if problem:
                errors.append(problem)
            target, target_problem = _posted_player(post, f"{prefix}_for_{order}", players)
            if target_problem:
                errors.append(target_problem)
            inning, inning_problem = _inning(post, f"{prefix}_inning_{order}", 7)
            if inning_problem:
                errors.append(inning_problem)
            situation = post.get(f"{prefix}_when_{order}") or "tied_or_trailing"
            if situation not in PH_VALUES:
                errors.append("Pick when the pinch hitter should be used.")
                situation = "tied_or_trailing"
            if player is None:
                continue
            if is_pitcher(player):
                errors.append(f"{player_label(player)} is a pitcher and cannot pinch hit.")
            if target is not None and target.mlb_id == player.mlb_id:
                errors.append(f"{player_label(player)} cannot pinch hit for himself.")
            pinch_hits.append(
                {
                    "vs_hand": hand,
                    "order": order,
                    "player": player,
                    "for_player": target,
                    "earliest_inning": inning,
                    "situation": situation,
                }
            )

    defense = []
    for order in range(1, DEFENSE_ROWS + 1):
        leaving, leave_problem = _posted_player(post, f"def_out_{order}", players)
        arriving, arrive_problem = _posted_player(post, f"def_in_{order}", players)
        if leave_problem:
            errors.append(leave_problem)
        if arrive_problem:
            errors.append(arrive_problem)
        inning, inning_problem = _inning(post, f"def_inning_{order}", 8)
        if inning_problem:
            errors.append(inning_problem)
        situation = post.get(f"def_when_{order}") or "leading"
        if situation not in DEFENSE_VALUES:
            errors.append("Pick when the defensive replacement should enter.")
            situation = "leading"
        if leaving is None and arriving is None:
            continue
        if leaving is None or arriving is None:
            errors.append(f"Defensive replacement {order} needs the player leaving and the player entering.")
            continue
        if is_pitcher(leaving) or is_pitcher(arriving):
            errors.append("Defensive replacements are position players.")
        if leaving.mlb_id == arriving.mlb_id:
            errors.append(f"{player_label(leaving)} cannot replace himself.")
        defense.append(
            {
                "order": order,
                "out_player": leaving,
                "in_player": arriving,
                "earliest_inning": inning,
                "situation": situation,
            }
        )

    pinch_runs = []
    for order in range(1, RUN_ROWS + 1):
        player, problem = _posted_player(post, f"pr_{order}", players)
        if problem:
            errors.append(problem)
        target, target_problem = _posted_player(post, f"pr_for_{order}", players)
        if target_problem:
            errors.append(target_problem)
        inning, inning_problem = _inning(post, f"pr_inning_{order}", 7)
        if inning_problem:
            errors.append(inning_problem)
        situation = post.get(f"pr_when_{order}") or "close"
        if situation not in RUN_VALUES:
            errors.append("Pick when the pinch runner should be used.")
            situation = "close"
        if player is None:
            continue
        if is_pitcher(player):
            errors.append(f"{player_label(player)} is a pitcher and cannot pinch run.")
        pinch_runs.append(
            {
                "order": order,
                "player": player,
                "for_player": target,
                "earliest_inning": inning,
                "situation": situation,
            }
        )
    return {
        "steal": steal,
        "bunt": bunt,
        "hit_and_run": hit_and_run,
        "pinch_hits": pinch_hits,
        "defense": defense,
        "pinch_runs": pinch_runs,
    }, errors


def _touch(plan, flag):
    setattr(plan, flag, True)
    plan.submitted_at = timezone.now()
    plan.save()


@transaction.atomic
def save_lineup(plan, parsed, roster):
    errors = []
    errors += validate_lineup([(player, position) for player, position, _order in parsed["R"]], roster, "right-handed")
    errors += validate_lineup([(player, position) for player, position, _order in parsed["L"]], roster, "left-handed")
    if errors:
        raise PlanError(errors)
    plan.lineup_slots.all().delete()
    rows = []
    for hand, slots in parsed.items():
        for player, position, order in slots:
            rows.append(models.LineupSlot(plan=plan, hand=hand, order=order, position=position, player=player))
    models.LineupSlot.objects.bulk_create(rows)
    _touch(plan, "lineup_saved")


@transaction.atomic
def save_rotation(plan, slots):
    if any(player is None for player in slots) or len(slots) != 6:
        raise PlanError(["Name a starter for each of the six games."])
    plan.rotation_slots.all().delete()
    models.RotationSlot.objects.bulk_create(
        [models.RotationSlot(plan=plan, game_number=number, player=player) for number, player in enumerate(slots, start=1)]
    )
    _touch(plan, "rotation_saved")


@transaction.atomic
def save_bullpen(plan, parsed):
    groups = parsed["groups"]
    errors = []
    if parsed["usage"] == "traditional" and not groups["closer"]:
        errors.append("Traditional usage needs a closer.")
    if not any(groups.values()):
        errors.append("Name at least one reliever.")
    seen = [player.mlb_id for role, players in groups.items() for player in players]
    if len(set(seen)) != len(seen):
        errors.append("A pitcher is listed twice in the bullpen.")
    if errors:
        raise PlanError(errors)
    plan.usage = parsed["usage"]
    plan.hook = parsed["hook"]
    plan.save(update_fields=["usage", "hook", "last_modified"])
    plan.bullpen_slots.all().delete()
    rows = []
    for role, _count in BULLPEN_SLOTS:
        for order, player in enumerate(groups[role], start=1):
            rows.append(models.BullpenSlot(plan=plan, role=role, order=order, player=player))
    models.BullpenSlot.objects.bulk_create(rows)
    _touch(plan, "bullpen_saved")


@transaction.atomic
def save_bench(plan, parsed):
    plan.steal = parsed["steal"]
    plan.bunt = parsed["bunt"]
    plan.hit_and_run = parsed["hit_and_run"]
    plan.save(update_fields=["steal", "bunt", "hit_and_run", "last_modified"])
    plan.pinch_hits.all().delete()
    plan.defense_subs.all().delete()
    plan.pinch_runs.all().delete()
    models.PinchHitRule.objects.bulk_create(
        [
            models.PinchHitRule(
                plan=plan,
                vs_hand=row["vs_hand"],
                order=row["order"],
                player=row["player"],
                for_player=row["for_player"],
                earliest_inning=row["earliest_inning"],
                situation=row["situation"],
            )
            for row in parsed["pinch_hits"]
        ]
    )
    models.DefenseSub.objects.bulk_create(
        [
            models.DefenseSub(
                plan=plan,
                order=row["order"],
                out_player=row["out_player"],
                in_player=row["in_player"],
                earliest_inning=row["earliest_inning"],
                situation=row["situation"],
            )
            for row in parsed["defense"]
        ]
    )
    models.PinchRunRule.objects.bulk_create(
        [
            models.PinchRunRule(
                plan=plan,
                order=row["order"],
                player=row["player"],
                for_player=row["for_player"],
                earliest_inning=row["earliest_inning"],
                situation=row["situation"],
            )
            for row in parsed["pinch_runs"]
        ]
    )
    _touch(plan, "bench_saved")


def lineup_rows(plan, hand):
    if plan is None:
        return [{"order": order, "player_id": "", "position": ""} for order in range(1, 10)]
    stored = {slot.order: slot for slot in plan.lineup_slots.all() if slot.hand == hand}
    if not stored:
        return [{"order": order, "player_id": "", "position": ""} for order in range(1, 10)]
    return [
        {
            "order": order,
            "player_id": stored[order].player_id if order in stored else "",
            "position": stored[order].position if order in stored else "",
        }
        for order in range(1, 10)
    ]


def rotation_ids(plan):
    if plan is None:
        return [""] * 6
    stored = {slot.game_number: slot.player_id for slot in plan.rotation_slots.all()}
    if not stored:
        return [""] * 6
    return [stored.get(number, "") for number in range(1, 7)]


def bullpen_ids(plan):
    grouped = {role: [""] * count for role, count in BULLPEN_SLOTS}
    if plan is None:
        return grouped
    for slot in plan.bullpen_slots.all():
        if slot.role in grouped and slot.order <= len(grouped[slot.role]):
            grouped[slot.role][slot.order - 1] = slot.player_id
    return grouped


def script_from_plan(plan, game_number, opponent_throws):
    """The computer's script for one game of the week."""
    hand = "L" if (opponent_throws or "").upper().startswith("L") else "R"
    lineup = [
        slot.player
        for slot in plan.lineup_slots.all()
        if slot.hand == hand
    ]
    rotation = [slot.player for slot in plan.rotation_slots.all()]
    planned = next((slot.player for slot in plan.rotation_slots.all() if slot.game_number == game_number), None)
    groups = {role: [] for role, _count in BULLPEN_SLOTS}
    for slot in plan.bullpen_slots.all():
        groups.setdefault(slot.role, []).append(slot.player)
    pinch_hits = [
        PinchHit(
            player=rule.player,
            vs_hand=rule.vs_hand,
            for_player_id=rule.for_player_id,
            earliest_inning=rule.earliest_inning,
            situation=rule.situation,
        )
        for rule in plan.pinch_hits.all()
    ]
    defense = [
        DefenseMove(
            out_player_id=rule.out_player_id,
            player=rule.in_player,
            earliest_inning=rule.earliest_inning,
            situation=rule.situation,
        )
        for rule in plan.defense_subs.all()
    ]
    pinch_runs = [
        PinchRun(
            player=rule.player,
            for_player_id=rule.for_player_id,
            earliest_inning=rule.earliest_inning,
            situation=rule.situation,
        )
        for rule in plan.pinch_runs.all()
    ]
    return Script(
        rotation=rotation,
        planned_starter=planned,
        closer=groups.get("closer", []),
        sirp=groups.get("sirp", []),
        mirp=groups.get("mirp", []),
        mopup=groups.get("mopup", []),
        lefty=groups.get("lefty", []),
        righty=groups.get("righty", []),
        usage=plan.usage,
        hook=plan.hook,
        pinch_hit=pinch_hits,
        defense=defense,
        pinch_run=pinch_runs,
        steal=plan.steal,
        bunt=plan.bunt,
        hit_and_run=plan.hit_and_run,
        lineup=lineup,
    )
