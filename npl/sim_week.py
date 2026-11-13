"""Simulate one week of games and fold the box scores into the season."""

from npl import models
from npl.computer_manager import ComputerManager, starter
from npl.engine_client import EngineError
from npl.sim_cards import SimError, hitter_card, pitcher_card
from npl.sim_play import SideBook, play_game
from npl.sim_season import rebuild_sim_season
from npl.weekly_plan import script_from_plan


def simulate_week(season, week, engine):
    """Play the week's remaining games. Games that already have a score stay as they are."""
    games = list(
        models.WeekGame.objects.filter(series__week=week)
        .select_related("series__week", "series__home_team", "series__road_team")
        .order_by("series_id", "number")
    )
    plans = {
        (plan.team_id, plan.series_id): plan
        for plan in models.WeeklyPlan.objects.filter(series__week=week).prefetch_related(
            "lineup_slots__player",
            "rotation_slots__player",
            "bullpen_slots__player",
            "pinch_hits__player",
            "pinch_hits__for_player",
            "defense_subs__out_player",
            "defense_subs__in_player",
            "pinch_runs__player",
            "pinch_runs__for_player",
        )
    }
    cards = {
        card.player_id: card
        for card in models.PlayerWeekCard.objects.filter(season=season, week=week.number)
    }
    played = 0
    skipped = 0
    errors = []
    for game in games:
        if game.is_played:
            skipped += 1
            continue
        try:
            box = _one_game(game, plans, cards, season, engine)
        except (SimError, EngineError) as error:
            errors.append(f"{game}: {error}")
            continue
        game.road_score = box["score"]["away"]
        game.home_score = box["score"]["home"]
        game.box_score = box
        game.save(update_fields=["road_score", "home_score", "box_score", "last_modified"])
        played += 1
    rebuilt = rebuild_sim_season(season)
    result = {"played": played, "skipped": skipped, "errors": errors, **rebuilt}
    if errors:
        raise SimError([*errors, f"Played {played} and left {len(errors)} unplayed."])
    return result


def _one_game(game, plans, cards, season, engine):
    series = game.series
    road_plan = plans.get((series.road_team_id, series.id))
    home_plan = plans.get((series.home_team_id, series.id))
    road_starter = _starter(road_plan, series.road_team, game.number)
    home_starter = _starter(home_plan, series.home_team, game.number)
    road_book, road_club = _side(road_plan, series.road_team, road_starter, home_starter.throws, game.number, season, cards)
    home_book, home_club = _side(home_plan, series.home_team, home_starter, road_starter.throws, game.number, season, cards)
    road_park = f"park-{series.road_team_id}"
    home_park = f"park-{series.home_team_id}"
    fixture = {
        "postseason": False,
        "parks": [{"id": road_park, "run_factor": 1.0}, {"id": home_park, "run_factor": 1.0}],
        "weather": None,
        "away": {**road_club, "id": str(series.road_team_id), "name": series.road_team.name, "home_park_id": road_park},
        "home": {**home_club, "id": str(series.home_team_id), "name": series.home_team.name, "home_park_id": home_park},
    }
    seed = max(1, int(series.week.seed or 1)) * 100000 + series.id * 10 + game.number
    return play_game(engine, fixture, road_book, home_book, seed)


def _starter(plan, team, number):
    if plan is None or not plan.rotation_saved:
        raise SimError(f"{team.abbreviation} has no rotation filed for game {number}.")
    script = script_from_plan(plan, number, "R")
    choice = starter(script.planned_starter, script.rotation, lambda _player: None)
    if choice.player is None:
        raise SimError(f"{team.abbreviation} has no starter for game {number}.")
    return choice.player


def _side(plan, team, starter, opponent_throws, number, season, cards):
    if plan is None or not plan.lineup_saved:
        raise SimError(f"{team.abbreviation} has no lineup filed.")
    hand = "L" if (opponent_throws or "").upper().startswith("L") else "R"
    slots = [slot for slot in plan.lineup_slots.all() if slot.hand == hand]
    if len(slots) != 9:
        raise SimError(f"{team.abbreviation} has no lineup filed against {hand}handers.")
    script = script_from_plan(plan, number, opponent_throws)
    staff = [starter]
    seen = {starter.mlb_id}
    for group in (script.closer, script.sirp, script.mirp, script.mopup, script.lefty, script.righty, script.others):
        for player in group:
            if player is None or player.mlb_id in seen:
                continue
            staff.append(player)
            seen.add(player.mlb_id)

    hitting = {}
    players = {}
    names = {}
    lineup = []
    for slot in slots:
        talent = _hitting(cards, slot.player)
        lineup.append(hitter_card(slot.player, talent, slot.position))
        _remember(hitting, players, names, slot.player, talent)
    for player in _bench(plan):
        if player.mlb_id in hitting:
            continue
        _remember(hitting, players, names, player, _hitting(cards, player))

    pitcher_cards = {}
    pitchers = []
    for index, player in enumerate(staff):
        talent = _pitching(cards, player)
        card = pitcher_card(player, talent, season.year, index == 0)
        pitcher_cards[player.mlb_id] = card
        pitchers.append(card)
        names[player.mlb_id] = player.name
        players[player.mlb_id] = player
    book = SideBook(ComputerManager(script), players, hitting, pitcher_cards, starter.mlb_id, names)
    return book, {"lineup": lineup, "pitchers": pitchers}


def _bench(plan):
    players = []
    for rule in plan.pinch_hits.all():
        players.append(rule.player)
    for rule in plan.defense_subs.all():
        players.append(rule.in_player)
    for rule in plan.pinch_runs.all():
        players.append(rule.player)
    return [player for player in players if player is not None]


def _remember(hitting, players, names, player, talent):
    hitting[player.mlb_id] = talent
    players[player.mlb_id] = player
    names[player.mlb_id] = player.name


def _hitting(cards, player):
    return _talent(cards, player, "hitting")


def _pitching(cards, player):
    return _talent(cards, player, "pitching")


def _talent(cards, player, side):
    card = cards.get(player.mlb_id)
    block = ((card.true_talent or {}).get(side) or {}) if card else {}
    talent = block.get("talent") if isinstance(block, dict) else None
    if not talent:
        label = "hitting" if side == "hitting" else "pitching"
        raise SimError(f"{player.name} has no {label} card for this week.")
    return talent
