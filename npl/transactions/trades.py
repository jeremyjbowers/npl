"""Group ledger rows under the trade they belong to.

A trade is one record: an id and a date, naming every club. The ledger
lines under it are the receipts. Older sheet rows have no trade id, so
pieces that sit next to each other, on the same date, between the same
two clubs, are shown as one deal. A different pair of clubs stays a
different deal.
"""

from collections import defaultdict


def is_trade_row(row):
    kind = getattr(row, "transaction_type", None)
    if kind is not None:
        code = (getattr(kind, "code", None) or "").strip().lower()
        label = (getattr(kind, "transaction_type", None) or "").strip().lower()
        if code == "trade" or label == "trade":
            return True
    raw = (getattr(row, "raw_transaction_type", None) or "").strip().lower()
    return raw == "trade"


def _label(team, raw):
    if team is not None and getattr(team, "short_name", None):
        return team.short_name
    text = (raw or "").strip()
    return text or ""


def join_parties(names):
    names = [name for name in names if name]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) > 2:
        return ", ".join(names[:-1]) + f", and {names[-1]}"
    if names:
        return names[0]
    return ""


def parties_for(rows, trade=None):
    names = []
    if trade is not None:
        names = [team.short_name for team in trade.teams.all() if team.short_name]
    if not names:
        for row in rows:
            for label in (
                _label(getattr(row, "team", None), getattr(row, "raw_team", None)),
                _label(getattr(row, "acquiring_team", None), getattr(row, "raw_acquiring_team", None)),
            ):
                if label and label not in names:
                    names.append(label)
    return join_parties(sorted(names, key=str.lower))


def _pair(row):
    sides = []
    if getattr(row, "team_id", None):
        sides.append(("id", row.team_id))
    else:
        raw = (getattr(row, "raw_team", None) or "").strip().lower()
        if raw:
            sides.append(("raw", raw))
    if getattr(row, "acquiring_team_id", None):
        sides.append(("id", row.acquiring_team_id))
    else:
        raw = (getattr(row, "raw_acquiring_team", None) or "").strip().lower()
        if raw and raw != "-":
            sides.append(("raw", raw))
    if len(sides) < 2:
        return None
    return tuple(sorted(sides))


def _trade_block(rows):
    trade = rows[0].trade if getattr(rows[0], "trade_id", None) else None
    return {
        "kind": "trade",
        "trade": trade,
        "date": trade.date if trade is not None and trade.date else rows[0].date,
        "parties": parties_for(rows, trade),
        "rows": rows,
    }


def group_log(rows):
    """Blocks in the same order as ``rows``.

    A block is either ``{"kind": "rows", "rows": [...]}`` or a trade block
    with the parent trade, the date, the clubs, and the receipt rows.
    """
    rows = list(rows)
    by_trade = defaultdict(list)
    for row in rows:
        if getattr(row, "trade_id", None):
            by_trade[row.trade_id].append(row)

    used = set()
    blocks = []
    for index, row in enumerate(rows):
        if row.id in used:
            continue
        if getattr(row, "trade_id", None):
            members = by_trade[row.trade_id]
            for member in members:
                used.add(member.id)
            blocks.append(_trade_block(members))
            continue
        if is_trade_row(row):
            pair = _pair(row)
            members = [row]
            used.add(row.id)
            if pair and row.date:
                for later in rows[index + 1 :]:
                    if later.id in used or getattr(later, "trade_id", None):
                        break
                    if not is_trade_row(later) or later.date != row.date or _pair(later) != pair:
                        break
                    members.append(later)
                    used.add(later.id)
            blocks.append(_trade_block(members))
            continue
        used.add(row.id)
        blocks.append({"kind": "rows", "rows": [row]})

    merged = []
    for block in blocks:
        if block["kind"] == "rows" and merged and merged[-1]["kind"] == "rows":
            merged[-1]["rows"].extend(block["rows"])
        else:
            merged.append(block)
    return merged


def sends_for_proposal(proposal):
    """Pieces grouped by the club that sends them, originating club first."""
    buckets = []
    index = {}
    for asset in proposal.assets.all():
        club = asset.from_team or proposal.originating_team
        key = club.pk if club is not None else 0
        if key not in index:
            index[key] = {"club": club, "pieces": []}
            buckets.append(index[key])
        index[key]["pieces"].append(asset)
    origin = proposal.originating_team_id
    buckets.sort(key=lambda bucket: (0 if bucket["club"] is not None and bucket["club"].pk == origin else 1))
    return buckets
