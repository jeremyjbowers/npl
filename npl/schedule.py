"""A season of weekly series.

Twenty-seven weeks, six games in each series, 162 games a team. Lineups are
due the Monday of the week. The six games are simulated together that Sunday.

Inside each twelve-team league the draw is a home-and-home round robin, plus
one extra series against each division rival. Two interleague weeks, the 13th
and the 20th, give every team one home series and one road series outside
the league. The same clubs and seed always draw the same schedule.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q

from npl import models


GAMES_PER_WEEK = 6
SEASON_WEEKS = 27
INTRA_WEEKS = 25
INTERLEAGUE_INDEXES = (12, 19)
EXTRA_DIVISION_INDEXES = (6, 14, 22)

DIVISION = "division"
LEAGUE = "league"
INTERLEAGUE = "interleague"


class ScheduleError(Exception):
    pass


@dataclass
class PlannedSeries:
    home: object
    road: object
    games: int = GAMES_PER_WEEK


@dataclass
class PlannedWeek:
    number: int
    kind: str
    lineup_due: date
    simulated_on: date
    series: list = field(default_factory=list)


def team_key(team):
    pk = getattr(team, "pk", None)
    if pk is not None:
        return ("pk", pk)
    return ("abbr", team.abbreviation)


def monday_on_or_before(day):
    return day - timedelta(days=day.weekday())


def default_opening_day(year):
    return date(year, 3, 26)


def group_leagues(teams):
    """Two leagues, each with three divisions of four. Divisions are sorted, then the clubs."""
    leagues = {}
    for team in teams:
        if not getattr(team, "league_id", None) or not getattr(team, "division_id", None):
            label = team.abbreviation or str(team)
            raise ScheduleError(f"{label} needs a league and a division before a schedule can be drawn.")
        leagues.setdefault(team.league_id, {}).setdefault(team.division_id, []).append(team)

    if len(leagues) != 2:
        raise ScheduleError(f"A weekly schedule needs two leagues. This draw has {len(leagues)}.")

    grouped = []
    for league_id in sorted(leagues):
        divisions = leagues[league_id]
        if len(divisions) != 3:
            raise ScheduleError(f"League {league_id} has {len(divisions)} divisions. A schedule needs three.")
        division_lists = []
        for division_id in sorted(divisions):
            members = sorted(divisions[division_id], key=lambda club: ((club.abbreviation or ""), team_key(club)))
            if len(members) != 4:
                raise ScheduleError(
                    f"Division {division_id} has {len(members)} teams. A schedule needs four."
                )
            division_lists.append(members)
        grouped.append(division_lists)
    return grouped


def _circle_rounds(teams):
    """Each pair meets once. ``teams`` has an even length."""
    size = len(teams)
    if size < 2 or size % 2:
        raise ScheduleError("A round-robin week needs an even number of teams.")
    rotation = list(teams)
    rounds = []
    for _ in range(size - 1):
        pairs = [(rotation[index], rotation[size - 1 - index]) for index in range(size // 2)]
        rounds.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return rounds


def _assign_homes(rounds, rng):
    """One home park per meeting. The club with fewer homes so far gets the park."""
    home_count = {}
    assigned = []
    for pairs in rounds:
        week = []
        ordered = sorted(pairs, key=lambda pair: ((pair[0].abbreviation or ""), (pair[1].abbreviation or "")))
        for left, right in ordered:
            home_count.setdefault(team_key(left), 0)
            home_count.setdefault(team_key(right), 0)
            if home_count[team_key(left)] < home_count[team_key(right)]:
                home, road = left, right
            elif home_count[team_key(right)] < home_count[team_key(left)]:
                home, road = right, left
            elif rng.random() < 0.5:
                home, road = left, right
            else:
                home, road = right, left
            home_count[team_key(home)] += 1
            week.append(PlannedSeries(home=home, road=road))
        assigned.append(week)
    return assigned


def _flip(weeks):
    return [
        [PlannedSeries(home=series.road, road=series.home, games=series.games) for series in week]
        for week in weeks
    ]


def _division_extra_weeks(divisions, rng):
    """
    One extra meeting with each division rival.

    The shuffled order A B C D hosts so two clubs get two home series and two
    get one. The three rounds are a perfect matching, so nobody plays twice.
    """
    rounds = [[], [], []]
    for division in divisions:
        first, second, third, fourth = division
        pairings = [
            [PlannedSeries(home=first, road=second), PlannedSeries(home=third, road=fourth)],
            [PlannedSeries(home=first, road=third), PlannedSeries(home=fourth, road=second)],
            [PlannedSeries(home=second, road=third), PlannedSeries(home=fourth, road=first)],
        ]
        for index, pairing in enumerate(pairings):
            rounds[index].extend(pairing)
    order = list(range(3))
    rng.shuffle(order)
    return [rounds[index] for index in order]


def _stitch(double_round, extras):
    weeks = []
    double_index = 0
    extra_index = 0
    for index in range(INTRA_WEEKS):
        if index in EXTRA_DIVISION_INDEXES:
            weeks.append(extras[extra_index])
            extra_index += 1
        else:
            weeks.append(double_round[double_index])
            double_index += 1
    return weeks


def _intra_league(divisions, rng):
    copied = [list(division) for division in divisions]
    for division in copied:
        rng.shuffle(division)
    clubs = [team for division in copied for team in division]
    rng.shuffle(clubs)
    first_leg = _assign_homes(_circle_rounds(clubs), rng)
    order = list(range(len(first_leg)))
    rng.shuffle(order)
    first_leg = [first_leg[index] for index in order]
    second_leg = _flip(first_leg)
    return_order = list(range(len(second_leg)))
    rng.shuffle(return_order)
    second_leg = [second_leg[index] for index in return_order]
    extras = _division_extra_weeks(copied, rng)
    return _stitch(first_leg + second_leg, extras), copied


def _interleague_weeks(first_divisions, second_divisions, rng):
    """Each club plays two opponents in the other league, one home and one away."""
    first = [team for division in first_divisions for team in division]
    second = [team for division in second_divisions for team in division]
    rng.shuffle(first)
    rng.shuffle(second)
    size = len(first)
    at_home = [PlannedSeries(home=first[index], road=second[index]) for index in range(size)]
    on_the_road = [
        PlannedSeries(home=second[index], road=first[(index + 1) % size]) for index in range(size)
    ]
    return [at_home, on_the_road]


def _same_division(series):
    return series.home.division_id == series.road.division_id and series.home.league_id == series.road.league_id


def _week_kind(series):
    if any(item.home.league_id != item.road.league_id for item in series):
        return INTERLEAGUE
    if all(_same_division(item) for item in series):
        return DIVISION
    return LEAGUE


def _combine(intra_weeks, inter_weeks, opening_day):
    monday = monday_on_or_before(opening_day)
    sequence = []
    intra_index = 0
    inter_index = 0
    for index in range(SEASON_WEEKS):
        if index in INTERLEAGUE_INDEXES:
            series = list(inter_weeks[inter_index])
            inter_index += 1
        else:
            series = list(intra_weeks[0][intra_index]) + list(intra_weeks[1][intra_index])
            intra_index += 1
        due = monday + timedelta(days=7 * index)
        sequence.append(
            PlannedWeek(
                number=index + 1,
                kind=_week_kind(series),
                lineup_due=due,
                simulated_on=due + timedelta(days=6),
                series=series,
            )
        )
    return sequence


def audit_plan(plan):
    """Raise ScheduleError unless the draw is a 162-game season with a legal weekly pairing."""
    if len(plan) != SEASON_WEEKS:
        raise ScheduleError(f"A season has {SEASON_WEEKS} weeks, and this draw has {len(plan)}.")

    meetings = {}
    homes = {}
    home_series = {}
    interleague_home = {}
    interleague_road = {}
    clubs = {}

    for week in plan:
        if len(week.series) != 12:
            raise ScheduleError(f"Week {week.number} has {len(week.series)} series. A week needs 12.")
        if week.lineup_due.weekday() != 0 or week.simulated_on != week.lineup_due + timedelta(days=6):
            raise ScheduleError(f"Week {week.number} does not run Monday to Sunday.")
        seen = set()
        for series in week.series:
            for club in (series.home, series.road):
                key = team_key(club)
                clubs[key] = club
                if key in seen:
                    raise ScheduleError(f"{club.abbreviation} plays twice in week {week.number}.")
                seen.add(key)
            pair = tuple(sorted((team_key(series.home), team_key(series.road))))
            meetings[pair] = meetings.get(pair, 0) + 1
            homes[(team_key(series.home), team_key(series.road))] = homes.get(
                (team_key(series.home), team_key(series.road)), 0
            ) + 1
            home_series[team_key(series.home)] = home_series.get(team_key(series.home), 0) + 1
            if series.home.league_id != series.road.league_id:
                interleague_home[team_key(series.home)] = interleague_home.get(team_key(series.home), 0) + 1
                interleague_road[team_key(series.road)] = interleague_road.get(team_key(series.road), 0) + 1

    if len(clubs) != 24:
        raise ScheduleError(f"A schedule needs 24 clubs, and this draw has {len(clubs)}.")

    for key, club in clubs.items():
        played = sum(1 for week in plan for series in week.series if team_key(series.home) == key or team_key(series.road) == key)
        if played != SEASON_WEEKS:
            raise ScheduleError(f"{club.abbreviation} has {played} series. A club plays {SEASON_WEEKS}.")
        if home_series.get(key, 0) not in (13, 14):
            raise ScheduleError(f"{club.abbreviation} hosts {home_series.get(key, 0)} series.")
        if interleague_home.get(key, 0) != 1 or interleague_road.get(key, 0) != 1:
            raise ScheduleError(f"{club.abbreviation} does not have one home and one road interleague series.")

    for (left, right), count in meetings.items():
        home_club = clubs[left]
        road_club = clubs[right]
        same_league = home_club.league_id == road_club.league_id
        same_division = same_league and home_club.division_id == road_club.division_id
        hosted = homes.get((left, right), 0)
        visited = homes.get((right, left), 0)
        if same_division and (count != 3 or sorted((hosted, visited)) != [1, 2]):
            raise ScheduleError(f"{home_club.abbreviation} and {road_club.abbreviation} do not split three division series.")
        if same_league and not same_division and (count != 2 or hosted != 1 or visited != 1):
            raise ScheduleError(f"{home_club.abbreviation} and {road_club.abbreviation} do not split a home and a road series.")
        if not same_league and count != 1:
            raise ScheduleError(f"{home_club.abbreviation} and {road_club.abbreviation} play {count} interleague series.")
    return plan


def build_season_plan(teams, seed, opening_day):
    """Draw the season. The same clubs and seed always produce the same weeks."""
    grouped = group_leagues(list(teams))
    rng = random.Random(seed)
    intra = []
    shuffled = []
    for divisions in grouped:
        weeks, copied = _intra_league(divisions, random.Random(rng.randrange(1, 2**31)))
        intra.append(weeks)
        shuffled.append(copied)
    inter = _interleague_weeks(shuffled[0], shuffled[1], random.Random(rng.randrange(1, 2**31)))
    plan = _combine(intra, inter, opening_day)
    return audit_plan(plan)


def season_games(season):
    return models.WeekGame.objects.filter(series__week__season=season)


def season_has_played_games(season):
    return season_games(season).filter(home_score__isnull=False, road_score__isnull=False).exists()


@transaction.atomic
def save_season_plan(season, plan, seed):
    """Replace the season's weeks. Played games, and the plans filed against them, stay put."""
    if season_has_played_games(season):
        raise ScheduleError(f"{season.year} has played games. Its schedule can no longer be regenerated.")
    audit_plan(plan)
    models.ScheduleWeek.objects.filter(season=season).delete()
    slot_count = series_count = game_count = 0
    for planned in plan:
        week = models.ScheduleWeek.objects.create(
            season=season,
            number=planned.number,
            kind=planned.kind,
            lineup_due=planned.lineup_due,
            simulated_on=planned.simulated_on,
            seed=seed,
        )
        slot_count += 1
        for planned_series in planned.series:
            series = models.WeekSeries.objects.create(
                week=week,
                home_team=planned_series.home,
                road_team=planned_series.road,
                games=planned_series.games,
            )
            series_count += 1
            models.WeekGame.objects.bulk_create(
                [
                    models.WeekGame(series=series, number=number)
                    for number in range(1, planned_series.games + 1)
                ]
            )
            game_count += planned_series.games
    return slot_count, series_count, game_count


def team_series(team, season):
    return (
        models.WeekSeries.objects.filter(week__season=season)
        .filter(Q(home_team=team) | Q(road_team=team))
        .select_related("week", "home_team", "road_team")
        .order_by("week__number")
    )
