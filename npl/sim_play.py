"""Play one game from the two weekly cards. Nobody sits it."""

import random

from npl.sim_box import box_from_results
from npl.sim_cards import SimError, hitter_card, pitcher_card

MAX_PLATE_APPEARANCES = 2000
STEAL_ATTEMPT = 0.15


def play_game(engine, fixture, away, home, seed):
    """
    ``away`` and ``home`` are ``SideBook`` values. Returns the box score.

    The engine resolves the plate appearance. This chooses the call, the
    reliever, and the pinch hitter from the weekly card before that.
    """
    names = {}
    names.update(away.names)
    names.update(home.names)
    books = {"away": away, "home": home}
    state = engine.start(fixture, seed)
    prepared = None
    rng = random.Random(seed)
    for index in range(MAX_PLATE_APPEARANCES):
        if state.get("status") == "final":
            break
        mark = (state.get("inning"), state.get("half"))
        if mark != prepared:
            state = _field_moves(engine, state, books)
            prepared = (state.get("inning"), state.get("half"))
        state = _batting_moves(engine, state, books)
        state = _pitching_move(engine, state, books, seed + index + 1)
        if state.get("status") == "final":
            break
        call = _call(state, books, rng)
        stepped = engine.step(state, seed + index + 1, call=call)
        state = stepped["state"]
    else:
        raise SimError("The game did not end.")
    if state.get("status") != "final":
        raise SimError("The game did not end.")
    return box_from_results(
        state.get("results") or [],
        names,
        state.get("line_score") or {},
        state.get("score") or {},
    )


def _field_moves(engine, state, books):
    side = _fielding(state)
    state = _clear_pending(engine, state, side)
    book = books[side]
    club = state[side]
    lineup_ids = {batter["id"] for batter in club.get("lineup") or []}
    moves = book.manager.defense(
        inning=int(state.get("inning") or 1),
        fielding_lead=_lead(state, side),
        lineup_ids=lineup_ids,
        problem=lambda player: _hitter_problem(book, player),
    )
    for out_id, player in moves:
        index = _index(club, out_id)
        if index is None:
            continue
        position = club["lineup"][index]["position"]
        state = engine.substitute(
            state,
            side,
            index,
            hitter_card(player, book.hitting[player.mlb_id], position),
            role="defense",
        )
        club = state[side]
    return state


def _clear_pending(engine, state, side):
    club = state[side]
    pending = set(club.get("pending") or [])
    if not pending:
        return state
    changes = []
    for index, batter in enumerate(club.get("lineup") or []):
        if batter["id"] in pending:
            changes.append({"index": index, "position": batter["position"], "defense": batter["defense"]})
    if not changes:
        return state
    return engine.set_positions(state, side, changes)


def _batting_moves(engine, state, books):
    side = _batting(state)
    book = books[side]
    club = state[side]
    lineup = club.get("lineup") or []
    if not lineup:
        return state
    index = int(club.get("batter_index") or 0) % len(lineup)
    batter = lineup[index]
    choice = book.manager.pinch_hit(
        inning=int(state.get("inning") or 1),
        batting_lead=_lead(state, side),
        pitcher_hand=_pitcher_hand(state, books, _fielding(state)),
        batter_id=batter["id"],
        problem=lambda player: _hitter_problem(book, player),
    )
    if choice.player is not None and choice.player.mlb_id != batter["id"]:
        state = engine.substitute(
            state,
            side,
            index,
            hitter_card(choice.player, book.hitting[choice.player.mlb_id], batter["position"]),
            role="pinch_hitter",
        )
        club = state[side]
    for base in ("first", "second", "third"):
        runner_id = (state.get("bases") or {}).get(base)
        if not runner_id:
            continue
        run = book.manager.pinch_run(
            inning=int(state.get("inning") or 1),
            batting_lead=_lead(state, side),
            runner_id=runner_id,
            problem=lambda player: _hitter_problem(book, player),
        )
        if run.player is None:
            continue
        slot = _index(club, runner_id)
        if slot is None:
            continue
        position = club["lineup"][slot]["position"]
        state = engine.substitute(
            state,
            side,
            slot,
            hitter_card(run.player, book.hitting[run.player.mlb_id], position),
            role="pinch_runner",
        )
        break
    return state


def _pitching_move(engine, state, books, seed):
    side = _fielding(state)
    book = books[side]
    club = state[side]
    pitcher_id = club.get("pitcher_slot")
    fatigue = (club.get("fatigue") or {}).get(pitcher_id) or {}
    spent = pitcher_id is None or (
        fatigue.get("ceiling") and fatigue.get("effort", 0) >= fatigue.get("ceiling")
    )
    hooked = pitcher_id is not None and book.manager.hook(fatigue) is not None
    if not spent and not hooked:
        return state
    batter_hand = _batter_hand(state, books, _batting(state))
    choice = book.manager.reliever(
        inning=int(state.get("inning") or 1),
        lead=_lead(state, side),
        runners_on=_runners(state),
        outs=int(state.get("outs") or 0),
        batter_hand=batter_hand,
        problem=lambda player: _pitcher_problem(club, book, player),
    )
    if choice.player is None or choice.player.mlb_id == pitcher_id:
        return state
    card = book.pitcher_cards[choice.player.mlb_id]
    return engine.bring_in_pitcher(state, card, seed)


def _call(state, books, rng):
    side = _batting(state)
    bases = state.get("bases") or {}
    occupied = {base: bool(bases.get(base)) for base in ("first", "second", "third")}
    call = books[side].manager.offense(
        inning=int(state.get("inning") or 1),
        outs=int(state.get("outs") or 0),
        bases=occupied,
        batting_lead=_lead(state, side),
        attempt_rate=STEAL_ATTEMPT,
        draw=rng.random(),
    )
    return call or "none"


def _hitter_problem(book, player):
    if player.mlb_id not in book.hitting:
        return "no hitting card"
    return None


def _pitcher_problem(club, book, player):
    if player.mlb_id == book.starter_id:
        return "he started today"
    if player.mlb_id in (club.get("unavailable") or []):
        return "already used"
    if player.mlb_id not in (club.get("available") or []):
        return "not in the pen"
    if player.mlb_id not in book.pitcher_cards:
        return "no pitching card"
    return None


def _fielding(state):
    return "home" if state.get("half") == "top" else "away"


def _batting(state):
    return "away" if state.get("half") == "top" else "home"


def _lead(state, side):
    score = state.get("score") or {}
    other = "home" if side == "away" else "away"
    return int(score.get(side) or 0) - int(score.get(other) or 0)


def _runners(state):
    bases = state.get("bases") or {}
    return sum(1 for base in ("first", "second", "third") if bases.get(base))


def _index(club, player_id):
    for index, batter in enumerate(club.get("lineup") or []):
        if batter["id"] == player_id:
            return index
    return None


def _batter_hand(state, books, side):
    club = state[side]
    lineup = club.get("lineup") or []
    if not lineup:
        return None
    batter = lineup[int(club.get("batter_index") or 0) % len(lineup)]
    player = books[side].players.get(batter["id"])
    return None if player is None else player.bats


def _pitcher_hand(state, books, side):
    pitcher_id = (state.get(side) or {}).get("pitcher_slot")
    player = books[side].players.get(pitcher_id)
    return None if player is None else player.throws


class SideBook:
    """One club's weekly card, in the shape the computer manager already reads."""

    def __init__(self, manager, players, hitting, pitcher_cards, starter_id, names):
        self.manager = manager
        self.players = players
        self.hitting = hitting
        self.pitcher_cards = pitcher_cards
        self.starter_id = starter_id
        self.names = names
