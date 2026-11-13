"""Build one week of player cards from the stat lines already on the players."""

from django.db import transaction

from npl.cards import build_card, majors_line
from npl.models import PlayerWeekCard


def _counts(card, side):
    if card is None:
        return None
    stored = (card.season_usage or {}).get(side)
    if not stored:
        return None
    return stored


def payload_for(player, season_year, week, previous):
    return build_card(
        majors_line(player, season_year - 1, "hit"),
        majors_line(player, season_year, "hit"),
        _counts(previous, "hitting"),
        majors_line(player, season_year - 1, "pitch"),
        majors_line(player, season_year, "pitch"),
        _counts(previous, "pitching"),
        week,
    )


def _store(payload):
    def side(name):
        block = payload.get(name)
        if not block:
            return None
        return {
            "talent": block["talent"],
            "prior": block["prior"],
            "usage_known": block["usage_known"],
        }

    hitting = payload.get("hitting")
    pitching = payload.get("pitching")
    return {
        "prior_weight": payload["prior_weight"],
        "true_talent": {
            "summary": payload["summary"],
            "prior_percent": payload["prior_percent"],
            "hitting": side("hitting"),
            "pitching": side("pitching"),
        },
        "week_usage": {
            "hitting": None if not hitting else hitting["week"],
            "pitching": None if not pitching else pitching["week"],
            "hitting_known": None if not hitting else hitting["usage_known"],
            "pitching_known": None if not pitching else pitching["usage_known"],
        },
        "season_usage": {
            "hitting": None if not hitting else hitting["season"],
            "pitching": None if not pitching else pitching["season"],
        },
    }


@transaction.atomic
def refresh_cards(season, week, players):
    """Write a card for each player. Returns how many were written."""
    previous = {}
    if week > 1:
        previous = {
            card.player_id: card
            for card in PlayerWeekCard.objects.filter(season=season, week=week - 1)
        }
    written = 0
    for player in players:
        payload = payload_for(player, season.year, week, previous.get(player.mlb_id))
        stored = _store(payload)
        PlayerWeekCard.objects.update_or_create(
            player=player,
            season=season,
            week=week,
            defaults=stored,
        )
        written += 1
    return written
