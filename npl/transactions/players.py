"""Match ledger names to player records, and list a player's own moves.

Archive rows store a name and sometimes an MLB id. The name is clickable
once ``Transaction.player`` is set. Matching prefers that id, then an
exact name, then one close name when no other player is as close.
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from nameparser import HumanName

from npl.transactions.catalog import sheet_asset_type
from npl.transactions.trades import trade_card_prefetches

SKIP_LABELS = {"", "-", "—"}
FUZZY_SCORE = 93
FUZZY_GAP = 4


def _strip(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", "").replace("’", "").replace(".", " ").replace("-", " ")
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    return " ".join(text.lower().split())


def _collapse_initials(text):
    tokens = text.split()
    collapsed = []
    buffer = ""
    for token in tokens:
        if len(token) == 1:
            buffer += token
            continue
        if buffer:
            collapsed.append(buffer)
            buffer = ""
        collapsed.append(token)
    if buffer:
        collapsed.append(buffer)
    return " ".join(collapsed)


def _parsed(text):
    return HumanName(text or "")


def _suffix(text):
    return _strip(_parsed(text).suffix)


def _last(text):
    parsed = _parsed(text)
    last = _strip(parsed.last)
    if last:
        return last
    tokens = _strip(text).split()
    return tokens[-1] if tokens else ""


def _identity(text):
    parsed = _parsed(text)
    parts = [
        _strip(parsed.first),
        _strip(parsed.middle),
        _strip(parsed.last),
        _strip(parsed.suffix),
    ]
    parts = [part for part in parts if part]
    if len(parts) >= 2:
        return _collapse_initials(" ".join(parts))
    return _collapse_initials(_strip(text))


def _token_key(text):
    return " ".join(sorted(_identity(text).split()))


def _id_keys(value):
    text = str(value or "").strip()
    if not text:
        return []
    keys = [text]
    digits = re.sub(r"\D", "", text)
    if digits and digits not in keys:
        keys.append(digits)
    stripped = digits.lstrip("0") if digits else ""
    if stripped and stripped not in keys:
        keys.append(stripped)
    return keys


def _unique(players):
    found = []
    seen = set()
    for player in players:
        if player.mlb_id in seen:
            continue
        seen.add(player.mlb_id)
        found.append(player)
    return found


@dataclass
class Match:
    player: object = None
    status: str = "unmatched"
    candidates: tuple = ()


class PlayerIndex:
    def __init__(self, players):
        self.by_id = {}
        self.by_key = defaultdict(list)
        self.by_last = defaultdict(list)
        id_buckets = defaultdict(list)
        for player in players:
            for key in _id_keys(player.mlb_id):
                id_buckets[key].append(player)
            labels = []
            if getattr(player, "name", None):
                labels.append(player.name)
            if getattr(player, "raw_name", None):
                labels.append(player.raw_name)
            first = getattr(player, "first_name", None)
            last = getattr(player, "last_name", None)
            if not labels and first and last:
                labels.append(f"{first} {last}")
            for label in labels:
                if not label or not str(label).strip():
                    continue
                self.by_key[_token_key(label)].append(player)
                last_name = _last(label)
                if last_name:
                    self.by_last[last_name].append(player)
        for key, group in id_buckets.items():
            unique = _unique(group)
            if len(unique) == 1:
                self.by_id[key] = unique[0]

    def match(self, raw_player, mlb_id=None):
        keys = _id_keys(mlb_id)
        if keys:
            for key in keys:
                player = self.by_id.get(key)
                if player is not None:
                    return Match(player, "mlb_id")
        label = (raw_player or "").strip()
        if label in SKIP_LABELS or sheet_asset_type(label) or len(_strip(label)) < 3:
            return Match(status="skip" if not keys else "unmatched")
        if keys:
            # The id did not match. Take an exact name, and do not guess.
            return self._exact(label)
        return self._by_name(label)

    def _exact(self, label):
        hits = _unique(self.by_key.get(_token_key(label), []))
        if len(hits) == 1:
            return Match(hits[0], "name")
        if len(hits) > 1:
            return Match(status="ambiguous", candidates=tuple(player.name for player in hits))
        return Match(status="unmatched")

    def _by_name(self, label):
        found = self._exact(label)
        if found.status != "unmatched":
            return found
        tokens = _strip(label).split()
        if len(tokens) == 1:
            hits = _unique(self.by_last.get(tokens[0], []))
            if len(hits) == 1 and _last(hits[0].name) == tokens[0]:
                return Match(hits[0], "name")
            if len(hits) > 1:
                return Match(status="ambiguous", candidates=tuple(player.name for player in hits))
            return Match(status="unmatched")
        return self._fuzzy(label)

    def _fuzzy(self, label):
        from fuzzywuzzy import fuzz

        last = _last(label)
        pool = list(self.by_last.get(last, []))
        if not pool and last:
            for candidate_last, players in self.by_last.items():
                if fuzz.ratio(last, candidate_last) >= FUZZY_SCORE:
                    pool.extend(players)
        query_suffix = _suffix(label)
        scored = []
        seen = set()
        identity = _identity(label)
        for player in pool:
            if player.mlb_id in seen:
                continue
            seen.add(player.mlb_id)
            if _suffix(player.name or "") != query_suffix:
                continue
            score = fuzz.token_sort_ratio(identity, _identity(player.name or ""))
            scored.append((score, player))
        if not scored:
            return Match(status="unmatched")
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0
        if best_score >= FUZZY_SCORE and best_score - second >= FUZZY_GAP:
            return Match(best, "fuzzy")
        if best_score >= FUZZY_SCORE:
            return Match(
                status="ambiguous",
                candidates=tuple(player.name for _score, player in scored if _score >= FUZZY_SCORE),
            )
        return Match(status="unmatched")


@dataclass
class LinkReport:
    mlb_id: int = 0
    name: int = 0
    fuzzy: int = 0
    skip: int = 0
    already_linked: int = 0
    ambiguous: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)


def apply_player_links():
    """Set ``player`` on ledger rows whose name or MLB id matches one player."""
    from npl.models import Player, Transaction

    index = PlayerIndex(
        Player.objects.all().only("mlb_id", "name", "first_name", "last_name", "raw_name")
    )
    report = LinkReport(already_linked=Transaction.objects.exclude(player__isnull=True).count())
    pending = list(
        Transaction.objects.filter(player__isnull=True).only("id", "raw_player", "mlb_id")
    )
    updates = []
    for row in pending:
        found = index.match(row.raw_player, row.mlb_id)
        if found.status == "skip":
            report.skip += 1
            continue
        if found.status == "ambiguous":
            report.ambiguous.append((row.raw_player or row.mlb_id or "", found.candidates))
            continue
        if found.player is None:
            label = (row.raw_player or "").strip()
            if label and label not in SKIP_LABELS and not sheet_asset_type(label):
                report.unmatched.append(label)
            else:
                report.skip += 1
            continue
        updates.append((row, found))
    for row, found in updates:
        fields = {"player_id": found.player.mlb_id}
        if not (row.mlb_id or "").strip():
            fields["mlb_id"] = found.player.mlb_id
        Transaction.objects.filter(pk=row.pk, player__isnull=True).update(**fields)
        setattr(report, found.status, getattr(report, found.status) + 1)
    return report


def ledger_for_player(player):
    """Ledger lines that name this player, newest first."""
    from django.db.models import Q

    from npl.models import Transaction

    return (
        Transaction.objects.filter(Q(player_id=player.pk) | Q(mlb_id=player.pk))
        .select_related("player", "team", "acquiring_team", "transaction_type", "trade")
        .defer(
            "player__stats",
            "player__scoresheet_defense",
            "player__scoresheet_offense",
        )
        .prefetch_related(*trade_card_prefetches())
        .order_by("-date", "-id")
    )
