"""The computer manager for a week that nobody sits.

ULMG's manager walks a half plan and takes the first legal player. NPL keeps
that order for the starter, the hook, and the bullpen windows. Managers here
cannot take a seat during a game, so the same manager also carries the
scoresheet instructions: which reliever faces a lefty, when the mop-up arms
work, who pinch hits, who replaces whom on defense, and who runs.

A player object needs an ``id``. ``problem(player)`` returns a reason or None.
"""

from dataclasses import dataclass, field


CLOSER = "closer"
SIRP = "sirp"
MIRP = "mirp"
MOPUP = "mopup"
LEFTY = "lefty"
RIGHTY = "righty"
OTHER = "other"

ROLE_LABELS = {
    CLOSER: "closer",
    SIRP: "setup",
    MIRP: "long relief",
    MOPUP: "mop-up",
    LEFTY: "lefty specialist",
    RIGHTY: "righty specialist",
    OTHER: "other arms",
}

FALLBACK_ORDER = (MIRP, SIRP, CLOSER)
SAVE_MAX_LEAD = 3
CLOSE_RUNS = 3
BLOWOUT = 4

BULLPEN_CHOICES = (
    ("traditional", "Traditional closer"),
    ("leverage", "Highest leverage"),
    ("fireman", "Fireman"),
    ("protect", "Protect the lead"),
    ("save", "Save the pen"),
    ("quick", "Good arms from the 6th"),
    ("slow", "Hold them until the 8th"),
)
HOOK_CHOICES = (
    ("quick", "Quick hook"),
    ("normal", "Normal hook"),
    ("slow", "Slow hook"),
)
STEAL_CHOICES = (
    ("never", "Never"),
    ("conservative", "Conservative"),
    ("normal", "Normal"),
    ("aggressive", "Aggressive"),
)
BUNT_CHOICES = (
    ("never", "Never"),
    ("sacrifice", "Sacrifice in a one-run game from the 7th"),
)
HIT_AND_RUN_CHOICES = (
    ("never", "Never"),
    ("normal", "With a runner on first and one out"),
)
PH_SITUATIONS = (
    ("trailing", "When trailing"),
    ("tied_or_trailing", "When tied or trailing"),
    ("any", "Any score"),
)
DEFENSE_SITUATIONS = (
    ("leading", "When leading"),
    ("tied_or_leading", "When tied or leading"),
    ("any", "Any score"),
)
RUN_SITUATIONS = (
    ("close", "Within a run"),
    ("any", "Any score"),
)

HOOK_CEILING_SHARE = {"quick": 0.85, "normal": 0.95, "slow": 1.00}
HOOK_RUNS = {"quick": 4, "normal": 5, "slow": 6}
DEFAULT_HOOK = "normal"
DEFAULT_BULLPEN = "traditional"
STEAL_SCALE = {"never": 0.0, "conservative": 0.5, "normal": 1.0, "aggressive": 1.5}


def _usage(
    note,
    *,
    sirp_innings=(),
    sirp_from=None,
    closer_first=9,
    closer="save",
    sirp_min_lead=0,
    sirp_max_lead=SAVE_MAX_LEAD,
    closer_max_lead=None,
    closer_min_lead=1,
):
    return {
        "note": note,
        "sirp_innings": sirp_innings,
        "sirp_from": sirp_from,
        "sirp_min_lead": sirp_min_lead,
        "sirp_max_lead": sirp_max_lead,
        "closer_first": closer_first,
        "closer": closer,
        "closer_max_lead": closer_max_lead,
        "closer_min_lead": closer_min_lead,
    }


_TRADITIONAL = _usage(
    "The closer pitches the ninth or later in a save situation. Setup pitches from the sixth "
    "on when the game is within three runs. Long relief works before the sixth, or when the game is not that close.",
    sirp_from=6,
    sirp_min_lead=-CLOSE_RUNS,
    sirp_max_lead=CLOSE_RUNS,
)
BULLPEN_WINDOWS = {
    "traditional": _TRADITIONAL,
    "normal": _TRADITIONAL,
    "leverage": _usage(
        "The closer comes in from the seventh on for a one- or two-run save, a ninth-inning save, "
        "or a one-run game or a tie with a runner on. Setup pitches the sixth, seventh and eighth "
        "when the lead is three or fewer and the closer stays in the pen. Long relief works the rest.",
        sirp_innings=(6, 7, 8),
        closer_first=7,
        closer="traffic",
    ),
    "quick": _usage(
        "Setup in the 6th, 7th and 8th, tied or leading by 3 or fewer. "
        "The closer from the 8th on, in a save situation. Long relief otherwise.",
        sirp_innings=(6, 7, 8),
        closer_first=8,
    ),
    "fireman": _usage(
        "The closer is a multi-inning ace. From the sixth on he pitches a tie or a one-run lead, "
        "and from the eighth on a save, and he stays while that is still true. Setup holds a two- or "
        "three-run lead in the seventh and eighth. Long relief works the rest.",
        sirp_innings=(7, 8),
        closer_first=6,
        closer="fireman",
        sirp_min_lead=2,
    ),
    "protect": _usage(
        "A lead gets the good arms. Setup pitches the seventh and eighth when leading by one, two or three. "
        "The closer pitches the ninth or later whenever the lead is three or fewer, save or not. "
        "Tied or trailing, long relief works.",
        sirp_innings=(7, 8),
        closer_first=9,
        closer="lead",
        sirp_min_lead=1,
        closer_max_lead=SAVE_MAX_LEAD,
    ),
    "save": _usage(
        "The closer pitches the ninth only in a save of one or two runs. Setup pitches the eighth "
        "only in a tie or a one-run lead. Long relief works the rest.",
        sirp_innings=(8,),
        closer_first=9,
        closer_max_lead=2,
        sirp_max_lead=1,
    ),
    "slow": _usage(
        "Setup in the 8th, tied or leading by 3 or fewer. "
        "The closer from the 9th on, in a save situation. Long relief otherwise.",
        sirp_innings=(8,),
        closer_first=9,
    ),
}


@dataclass
class Choice:
    """The player chosen, or None, and who was passed over on the way."""

    player: object = None
    skipped: list = field(default_factory=list)
    group: str = None


@dataclass
class PinchHit:
    player: object
    vs_hand: str = "any"
    for_player_id: object = None
    earliest_inning: int = 7
    situation: str = "tied_or_trailing"


@dataclass
class DefenseMove:
    out_player_id: object
    player: object
    earliest_inning: int = 8
    situation: str = "leading"


@dataclass
class PinchRun:
    player: object
    for_player_id: object = None
    earliest_inning: int = 7
    situation: str = "close"


@dataclass
class Script:
    """Everything the computer needs for one game, copied off the weekly card."""

    rotation: list = field(default_factory=list)
    planned_starter: object = None
    closer: list = field(default_factory=list)
    sirp: list = field(default_factory=list)
    mirp: list = field(default_factory=list)
    mopup: list = field(default_factory=list)
    lefty: list = field(default_factory=list)
    righty: list = field(default_factory=list)
    others: list = field(default_factory=list)
    usage: str = DEFAULT_BULLPEN
    hook: str = DEFAULT_HOOK
    pinch_hit: list = field(default_factory=list)
    defense: list = field(default_factory=list)
    pinch_run: list = field(default_factory=list)
    steal: str = "normal"
    bunt: str = "never"
    hit_and_run: str = "never"
    lineup: list = field(default_factory=list)


def _first_legal(candidates, problem):
    choice = Choice()
    seen = set()
    for player in candidates:
        if player is None or player.id in seen:
            continue
        seen.add(player.id)
        reason = problem(player)
        if reason is None:
            choice.player = player
            return choice
        choice.skipped.append((player, reason))
    return choice


def starter(planned, rotation, problem):
    """Planned starter, or the next legal arm in the rotation after him."""
    rotation = list(rotation)
    if planned is not None and planned in rotation:
        index = rotation.index(planned)
        order = [planned] + rotation[index + 1:] + rotation[:index]
    else:
        order = [planned] + rotation
    return _first_legal(order, problem)


def _window(logic):
    return BULLPEN_WINDOWS.get(logic, BULLPEN_WINDOWS[DEFAULT_BULLPEN])


def describe_bullpen_logic(logic):
    return _window(logic)["note"]


def is_save_situation(lead, runners_on, outs):
    """Rule 9.19 for a pitcher entering in the ninth or later."""
    if lead <= 0:
        return False
    if lead <= SAVE_MAX_LEAD and outs == 0:
        return True
    return lead <= runners_on + 2


def _calls_closer(window, inning, lead, runners_on, outs):
    if inning < window["closer_first"]:
        return False
    mode = window["closer"]
    save = is_save_situation(lead, runners_on, outs)
    if mode == "save":
        cap = window["closer_max_lead"]
        return save and (cap is None or lead <= cap)
    if mode == "lead":
        return window["closer_min_lead"] <= lead <= window["closer_max_lead"]
    if mode == "fireman":
        if lead in (0, 1):
            return True
        return inning >= 8 and save
    if mode == "traffic":
        cap = window["closer_max_lead"]
        if inning >= 9 and save and (cap is None or lead <= cap):
            return True
        if save and 0 < lead <= 2:
            return True
        return lead in (-1, 0, 1) and runners_on >= 1
    return False


def _calls_sirp(window, inning, lead):
    if not window["sirp_min_lead"] <= lead <= window["sirp_max_lead"]:
        return False
    if window["sirp_from"] is not None and inning >= window["sirp_from"]:
        return True
    return inning in window["sirp_innings"]


def bullpen_role(inning, lead, runners_on, outs, logic=None):
    """The role this spot calls for. ``lead`` is the fielding side's run margin."""
    if lead <= -BLOWOUT or lead >= BLOWOUT + 1:
        return MOPUP
    window = _window(logic)
    if _calls_closer(window, inning, lead, runners_on, outs):
        return CLOSER
    if _calls_sirp(window, inning, lead):
        return SIRP
    return MIRP


def group_order(role):
    if role == MOPUP:
        return [MOPUP, MIRP, OTHER, SIRP, CLOSER]
    return [role] + [group for group in FALLBACK_ORDER if group != role] + [OTHER]


def _first_in_groups(order, groups, problem):
    choice = Choice()
    seen = set()
    for group in order:
        players = [player for player in groups.get(group, []) if player is not None and player.id not in seen]
        seen |= {player.id for player in players}
        found = _first_legal(players, problem)
        choice.skipped += found.skipped
        if found.player is not None:
            choice.player = found.player
            choice.group = group
            return choice
    return choice


def reliever(role, groups, problem, batter_hand=None):
    """
    The arm for this spot. In a closer or setup inning, a specialist who
    matches the batter's hand is tried before the role's own list.
    """
    if role in (CLOSER, SIRP) and batter_hand in ("L", "R"):
        specialist = LEFTY if batter_hand == "L" else RIGHTY
        found = _first_in_groups([specialist], groups, problem)
        if found.player is not None:
            return found
    return _first_in_groups(group_order(role), groups, problem)


def hook_reason(hook, fatigue):
    """Why the starter's hook pulls him, or None. The engine's own fatigue line still applies."""
    hook = hook if hook in HOOK_RUNS else DEFAULT_HOOK
    runs = fatigue.get("runs_allowed", 0)
    if runs >= HOOK_RUNS[hook]:
        return f"he has allowed {runs} runs, and a {hook} hook pulls a starter at {HOOK_RUNS[hook]}."
    share = HOOK_CEILING_SHARE[hook]
    ceiling = fatigue.get("ceiling") or 0
    effort = fatigue.get("effort", 0)
    if ceiling > 0 and effort >= share * ceiling:
        return (
            f"he has spent {effort / ceiling:.0%} of his fatigue ceiling, "
            f"and a {hook} hook pulls a starter at {share:.0%}."
        )
    return None


def is_steal_situation(bases, outs):
    return bool(bases.get("first")) and not bases.get("second") and outs < 2


def calls_steal(attempt_rate, draw):
    return attempt_rate is not None and draw < attempt_rate


def _score_ok(situation, lead):
    if situation == "any":
        return True
    if situation == "trailing":
        return lead < 0
    if situation == "tied_or_trailing":
        return lead <= 0
    if situation == "leading":
        return lead > 0
    if situation == "tied_or_leading":
        return lead >= 0
    if situation == "close":
        return -1 <= lead <= 1
    return False


def _hand_ok(vs_hand, pitcher_hand):
    if vs_hand in (None, "", "any"):
        return True
    return (pitcher_hand or "").upper().startswith(vs_hand.upper())


def pinch_hitter(rules, *, inning, batting_lead, pitcher_hand, batter_id, problem):
    """First listed pinch hitter whose inning, score, hand, and optional target match."""
    candidates = []
    for rule in rules:
        if inning < rule.earliest_inning:
            continue
        if not _score_ok(rule.situation, batting_lead):
            continue
        if not _hand_ok(rule.vs_hand, pitcher_hand):
            continue
        if rule.for_player_id not in (None, batter_id):
            continue
        candidates.append(rule.player)
    return _first_legal(candidates, problem)


def defensive_replacements(rules, *, inning, fielding_lead, lineup_ids, problem):
    """Replacements that apply at the start of a half inning in the field."""
    moves = []
    used_out = set()
    used_in = set()
    for rule in rules:
        if inning < rule.earliest_inning:
            continue
        if not _score_ok(rule.situation, fielding_lead):
            continue
        if rule.out_player_id not in lineup_ids or rule.out_player_id in used_out:
            continue
        if rule.player is None or rule.player.id in used_in:
            continue
        reason = problem(rule.player)
        if reason:
            continue
        used_out.add(rule.out_player_id)
        used_in.add(rule.player.id)
        moves.append((rule.out_player_id, rule.player))
    return moves


def pinch_runner(rules, *, inning, batting_lead, runner_id, problem):
    """A pinch runner for this baserunner, or None."""
    candidates = []
    for rule in rules:
        if inning < rule.earliest_inning:
            continue
        if not _score_ok(rule.situation, batting_lead):
            continue
        if rule.for_player_id not in (None, runner_id):
            continue
        candidates.append(rule.player)
    return _first_legal(candidates, problem)


def offensive_call(script, *, inning, outs, bases, batting_lead, attempt_rate, draw):
    """
    The call for this plate appearance, or None.

    A sacrifice is taken in a one-run game from the seventh with nobody out
    and a runner on. A hit-and-run is the one-out version of that same spot
    when the manager asked for it. Steals use the runner's attempt rate,
    scaled by the weekly setting.
    """
    runner_on = bool(bases.get("first") or bases.get("second") or bases.get("third"))
    within_one = -1 <= batting_lead <= 1
    if script.bunt == "sacrifice" and inning >= 7 and outs == 0 and runner_on and within_one:
        return "bunt"
    if (
        script.hit_and_run == "normal"
        and is_steal_situation(bases, outs)
        and outs == 1
        and within_one
        and draw < 0.08
    ):
        return "hit_and_run"
    if is_steal_situation(bases, outs) and script.steal != "never":
        scale = STEAL_SCALE.get(script.steal, 1.0)
        rate = 0 if attempt_rate is None else min(1.0, attempt_rate * scale)
        if calls_steal(rate, draw):
            return "steal"
    return None


class ComputerManager:
    """The decisions for one game, read off a weekly script."""

    def __init__(self, script):
        self.script = script

    def groups(self):
        script = self.script
        return {
            CLOSER: list(script.closer),
            SIRP: list(script.sirp),
            MIRP: list(script.mirp),
            MOPUP: list(script.mopup),
            LEFTY: list(script.lefty),
            RIGHTY: list(script.righty),
            OTHER: list(script.others),
        }

    def starter(self, problem):
        return starter(self.script.planned_starter, self.script.rotation, problem)

    def reliever(self, *, inning, lead, runners_on, outs, batter_hand, problem):
        role = bullpen_role(inning, lead, runners_on, outs, self.script.usage)
        return reliever(role, self.groups(), problem, batter_hand=batter_hand)

    def hook(self, fatigue):
        return hook_reason(self.script.hook, fatigue)

    def pinch_hit(self, **kwargs):
        return pinch_hitter(self.script.pinch_hit, **kwargs)

    def defense(self, **kwargs):
        return defensive_replacements(self.script.defense, **kwargs)

    def pinch_run(self, **kwargs):
        return pinch_runner(self.script.pinch_run, **kwargs)

    def offense(self, **kwargs):
        return offensive_call(self.script, **kwargs)
