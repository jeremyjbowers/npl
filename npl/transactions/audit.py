"""Checks for every defined transaction type, and for the league sheet.

The 2025 and 2026 transaction tabs are the logs on the league workbook.
Earlier seasons are not on that sheet. ``director_audit`` files each type,
posts a ledger row, and rolls the whole run back so a director can read
the result without changing a roster.
"""

import datetime
import json
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from npl import models
from npl.management.commands.initial_load_transactions import parse_transaction_row
from npl.transactions.catalog import (
    ASSET_LABELS,
    CATEGORIES,
    KINDS,
    SHEET_ALIASES,
    normalize_sheet_type,
    sheet_asset_qualifier,
    sheet_asset_type,
)
from npl.transactions.service import agree, create_proposal, execute_proposal

CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "transaction_sheet_corpus.json"
EASTERN = ZoneInfo("America/New_York")
CITATION = "https://npl.example/audit"

ROSTER_FIELDS = (
    "roster_40man",
    "roster_7dayIL",
    "roster_56dayIL",
    "roster_eosIL",
    "roster_restricted",
    "roster_tripleA",
    "roster_tripleA_option",
    "roster_outrighted",
    "roster_foreign",
    "roster_retired",
    "roster_nonroster",
    "roster_doubleA",
    "roster_singleA",
)

IL_OPEN = {"il_7": "7", "il_56": "56", "il_eos": "eos", "il_covid": "covid"}

# How to put a club and a player in a state where this type is legal.
# Phase follows the published rules: IL and options are regular season,
# nontenders are offseason.
SETUP = {
    "il_7": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "il_56": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}, "fill_40": True},
    "il_eos": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}, "notes": CITATION},
    "il_covid": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "il_move": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True, "roster_7dayIL": True}},
    "il_activate": {
        "phase": models.Season.REGULAR,
        "home": "club",
        "roster": {"roster_40man": True, "roster_7dayIL": True},
        "pre_il": True,
    },
    "in_limbo": {"phase": models.Season.REGULAR, "home": "club", "limbo_reason": "pending_trade"},
    "option_minors": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "recall_option": {
        "phase": models.Season.REGULAR,
        "home": "club",
        "roster": {"roster_40man": True, "roster_tripleA_option": True},
    },
    "purchase_contract": {
        "phase": models.Season.REGULAR,
        "home": "club",
        "roster": {"roster_tripleA": True},
        "contract": True,
    },
    "release": {"phase": models.Season.REGULAR, "home": "club"},
    "non_tender": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}},
    "restricted_place": {"phase": models.Season.REGULAR, "home": "club", "rl_type": "PED"},
    "restricted_activate": {
        "phase": models.Season.REGULAR,
        "home": "club",
        "roster": {"roster_restricted": True},
        "pre_rl": True,
    },
    "foreign_place": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}, "notes": CITATION},
    "foreign_reinstate": {
        "phase": models.Season.REGULAR,
        "home": "club",
        "roster": {"roster_40man": True, "roster_foreign": True},
    },
    "retirement": {"phase": models.Season.REGULAR, "home": "club"},
    "death": {"phase": models.Season.REGULAR, "home": "club"},
    "mlb_signing": {"phase": models.Season.OFFSEASON, "home": "free", "contract": True},
    "in_season_fa": {"phase": models.Season.REGULAR, "home": "free", "contract": True},
    "minor_signing": {"phase": models.Season.OFFSEASON, "home": "free", "contract": True},
    "ifa_signing": {"phase": models.Season.OFFSEASON, "home": "free", "contract": True},
    "extension": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}, "contract": True},
    "exercise_option": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}, "contract": True},
    "exercise_vesting_option": {
        "phase": models.Season.OFFSEASON,
        "home": "club",
        "roster": {"roster_40man": True},
        "contract": True,
    },
    "decline_option": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}, "contract": True},
    "qualifying_offer": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}, "contract": True},
    "contract_amnesty": {"phase": models.Season.OFFSEASON, "home": "club", "roster": {"roster_40man": True}},
    "waiver_request_outright": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "waiver_request_trade": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "waiver_cleared_outright": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "waiver_claimed": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_40man": True}},
    "waiver_request_rule5": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_tripleA": True}},
    "waiver_returned_rule5": {"phase": models.Season.REGULAR, "home": "club", "roster": {"roster_tripleA": True}},
    "rule5_draft": {"phase": models.Season.OFFSEASON, "home": "free"},
    "rule4_draft": {"phase": models.Season.OFFSEASON, "home": "free", "contract": True},
    "auction_result": {"phase": models.Season.REGULAR, "home": "free", "contract": True},
    "trade": {"phase": models.Season.REGULAR, "trade": True},
}

WAIVER_TYPES = {
    "waiver_request_outright": models.Waiver.OUTRIGHT,
    "waiver_request_trade": models.Waiver.TRADE,
    "waiver_request_rule5": models.Waiver.RULE5,
}


class AuditFailure(Exception):
    pass


def load_corpus():
    with CORPUS_PATH.open() as handle:
        return json.load(handle)


def _check(name, group, passed, detail, code=""):
    return {"name": name, "group": group, "code": code, "passed": passed, "detail": detail}


def _expect(condition, message):
    if not condition:
        raise AuditFailure(message)


def sheet_report():
    """Read-only checks against the frozen sheet corpus and the catalog."""
    corpus = load_corpus()
    checks = []
    problems = []
    labels = [kind["label"] for kind in KINDS.values()]
    if len(labels) != len(set(labels)):
        problems.append("Two types share a label.")
    if set(SETUP) != set(KINDS):
        missing = sorted(set(KINDS) - set(SETUP))
        extra = sorted(set(SETUP) - set(KINDS))
        if missing:
            problems.append("No filing setup for " + ", ".join(missing) + ".")
        if extra:
            problems.append("Filing setup names unknown types: " + ", ".join(extra) + ".")
    for kind in KINDS.values():
        if kind["category"] not in CATEGORIES:
            problems.append(f"{kind['label']} has an unknown category.")
    bad_aliases = [label for label, code in SHEET_ALIASES.items() if code not in KINDS]
    if bad_aliases:
        problems.append("Sheet aliases point at unknown types: " + ", ".join(sorted(bad_aliases)) + ".")
    checks.append(
        _check(
            "catalog",
            "catalog",
            not problems,
            " ".join(problems) if problems else f"The catalog defines {len(KINDS)} transaction types.",
        )
    )

    unmapped = corpus.get("unmapped_labels") or []
    checks.append(
        _check(
            "unmapped",
            "sheet",
            not unmapped,
            "Every dated label on the 2025 and 2026 tabs maps to a defined type."
            if not unmapped
            else "Unmapped sheet labels: " + ", ".join(unmapped) + ".",
        )
    )

    recognized = (corpus.get("source") or {}).get("recognized_rows") or {}
    counted = {"2025": 0, "2026": 0}
    for row in corpus.get("labels") or []:
        for year in ("2025", "2026"):
            counted[year] += int((row.get("counts") or {}).get(year) or 0)
    count_ok = counted["2025"] == int(recognized.get("2025") or -1) and counted["2026"] == int(
        recognized.get("2026") or -1
    )
    checks.append(
        _check(
            "counts",
            "sheet",
            count_ok,
            f"2025 has {counted['2025']} dated transactions and 2026 has {counted['2026']}."
            if count_ok
            else "The per-label counts do not add up to the tab totals.",
        )
    )

    label_rows = []
    for row in corpus.get("labels") or []:
        label = row["label"]
        code = normalize_sheet_type(label)
        example = row.get("example") or {}
        cells = example.get("cells") or []
        payload = parse_transaction_row(cells) if len(cells) >= 6 else None
        problems = []
        if code != row.get("code") or code not in KINDS:
            problems.append(f"{label!r} does not map to {row.get('code')}.")
        if payload is None:
            problems.append("The sample row did not parse.")
        elif payload["raw_transaction_type"].strip() != cells[5].strip():
            problems.append("The sample row changed the type text.")
        detail = _example_text(cells) if not problems else " ".join(problems)
        passed = not problems
        checks.append(_check(f"sheet:{label}", "sheet", passed, detail, code or ""))
        label_rows.append(
            {
                "label": label,
                "code": row.get("code") or "",
                "type_label": KINDS.get(row.get("code") or "", {}).get("label", ""),
                "count_2025": int(row["counts"].get("2025") or 0),
                "count_2026": int(row["counts"].get("2026") or 0),
                "example": _example_text(cells),
                "passed": passed,
                "detail": detail,
            }
        )

    piece_rows = []
    for row in corpus.get("pieces") or []:
        label = row["label"]
        problems = []
        if sheet_asset_type(label) != row.get("asset_type"):
            problems.append(f"{label!r} is not classified as {row.get('asset_type')}.")
        if sheet_asset_qualifier(label) != row.get("qualifier"):
            problems.append(f"{label!r} qualifier does not match the sheet.")
        checks.append(
            _check(
                f"piece-label:{label}",
                "sheet",
                not problems,
                " ".join(problems) if problems else f"{label} is a {ASSET_LABELS.get(row.get('asset_type'), row.get('asset_type'))}.",
                "",
            )
        )
        piece_rows.append(
            {
                "label": label,
                "asset_type": row.get("asset_type") or "",
                "asset_label": ASSET_LABELS.get(row.get("asset_type") or "", row.get("asset_type") or ""),
                "qualifier": row.get("qualifier") or "",
                "count_2025": int(row["counts"].get("2025") or 0),
                "count_2026": int(row["counts"].get("2026") or 0),
                "example": _example_text((row.get("example") or {}).get("cells") or []),
                "cells": (row.get("example") or {}).get("cells") or [],
                "passed": not problems,
                "detail": " ".join(problems),
            }
        )

    return {"corpus": corpus, "checks": checks, "labels": label_rows, "pieces": piece_rows}


def _example_text(cells):
    if len(cells) < 8:
        return ""
    bits = [cells[0], cells[1], cells[2], cells[5]]
    if cells[6].strip():
        bits.append("to " + cells[6].strip())
    if cells[7].strip():
        bits.append(cells[7].strip().replace("\n", " "))
    return ", ".join(bit for bit in bits if bit)


def director_audit(actor):
    """Run every check. Database writes in this call are rolled back."""
    with transaction.atomic():
        try:
            sheet = sheet_report()
            filings = _filing_checks(actor, sheet["pieces"])
            return _combine(sheet, filings)
        finally:
            transaction.set_rollback(True)


def _combine(sheet, filings):
    by_name = {item["name"]: item for item in filings}
    label_problems = {}
    for row in sheet["labels"]:
        if not row["passed"]:
            label_problems.setdefault(row["code"], []).append(f"{row['label']}: {row['detail']}")

    counts = {}
    names = {}
    for row in sheet["labels"]:
        bucket = counts.setdefault(row["code"], {"2025": 0, "2026": 0})
        bucket["2025"] += row["count_2025"]
        bucket["2026"] += row["count_2026"]
        names.setdefault(row["code"], []).append(row["label"])

    kinds = []
    for code, kind in KINDS.items():
        filing = by_name.get(f"filing:{code}")
        passed = bool(filing and filing["passed"]) and code not in label_problems
        detail = filing["detail"] if filing else "No filing check."
        if code in label_problems:
            detail = detail + " " + " ".join(label_problems[code])
        sheet_names = names.get(code) or []
        tally = counts.get(code) or {"2025": 0, "2026": 0}
        kinds.append(
            {
                "code": code,
                "label": kind["label"],
                "category": kind["category"].replace("_", " ").title(),
                "filer": "Club" if kind["manager_can_initiate"] else "Directors",
                "count_2025": tally["2025"],
                "count_2026": tally["2026"],
                "sheet_names": ", ".join(sheet_names) if sheet_names else "Not in the 2025 or 2026 transaction logs",
                "passed": passed,
                "detail": detail,
            }
        )

    pieces = []
    for row in sheet["pieces"]:
        filing = by_name.get(f"piece:{row['label']}")
        passed = row["passed"] and bool(filing and filing["passed"])
        detail = filing["detail"] if filing else row["detail"]
        if not row["passed"]:
            detail = (row["detail"] + " " + detail).strip()
        pieces.append({**row, "passed": passed, "detail": detail, "cells": None})

    checks = list(sheet["checks"]) + list(filings)
    failed = [item for item in checks if not item["passed"]]
    # Kind and piece rows repeat filing results. The summary counts each check once.
    recognized = (sheet["corpus"].get("source") or {}).get("recognized_rows") or {}
    ran = timezone.now().astimezone(EASTERN)
    return {
        "audit_ran_at": ran.strftime("%B %-d, %Y, %-I:%M %p ET"),
        "audit_passed": len(checks) - len(failed),
        "audit_failed": len(failed),
        "audit_failures": failed,
        "audit_kinds": kinds,
        "audit_labels": sheet["labels"],
        "audit_pieces": pieces,
        "audit_recognized_2025": int(recognized.get("2025") or 0),
        "audit_recognized_2026": int(recognized.get("2026") or 0),
        "checks": checks,
    }


def _filing_checks(actor, pieces):
    if not getattr(actor, "is_staff", False):
        return [_check("filing", "filing", False, "The audit has to be run by a director.")]

    token = uuid.uuid4().hex[:12]
    user_model = get_user_model()
    other_user = user_model.objects.create_user(email=f"audit-{token}@example.com", password="secret")
    other_owner = models.Owner.objects.create(name="Audit Counterparty", user=other_user)
    team = models.Team.objects.create(full_name="Audit Club", short_name=f"Audit{token[:6]}", abbreviation="AUD")
    other_team = models.Team.objects.create(full_name="Audit Other", short_name=f"Other{token[:6]}", abbreviation="AOT")
    other_team.owners.add(other_owner)
    player = models.Player.objects.create(
        mlb_id=f"npl-audit-{token}",
        name="Audit Player",
        first_name="Audit",
        last_name="Player",
        team=team,
        options=2,
    )
    season = models.Season.objects.create(year=2099, phase=models.Season.REGULAR, is_current=True)
    ctx = {
        "actor": actor,
        "team": team,
        "other_team": other_team,
        "other_user": other_user,
        "player": player,
        "season": season,
    }

    checks = []
    for code in KINDS:
        checks.append(_in_savepoint(f"filing:{code}", "filing", code, lambda code=code: _file_kind(ctx, code)))
    for piece in pieces:
        label = piece["label"]
        checks.append(
            _in_savepoint(
                f"piece:{label}",
                "piece",
                "",
                lambda piece=piece: _file_piece(ctx, piece),
            )
        )
    return checks


def _in_savepoint(name, group, code, run):
    sid = transaction.savepoint()
    try:
        detail = run()
        return _check(name, group, True, detail, code)
    except AuditFailure as exc:
        return _check(name, group, False, str(exc), code)
    except Exception as exc:
        return _check(name, group, False, f"{exc.__class__.__name__}: {exc}", code)
    finally:
        transaction.savepoint_rollback(sid)


def _file_kind(ctx, code):
    spec = SETUP.get(code)
    _expect(spec is not None, f"No filing setup for {code}.")
    kind = KINDS[code]
    player = ctx["player"]
    team = ctx["team"]
    season = ctx["season"]
    player.refresh_from_db()
    season.refresh_from_db()
    season.phase = spec["phase"]
    season.save(update_fields=["phase", "last_modified"])

    home = spec.get("home", "club")
    if spec.get("trade"):
        _reset_player(player, team, {})
    elif home == "free":
        _reset_player(player, None, spec.get("roster") or {})
    else:
        _reset_player(player, team, spec.get("roster") or {})
    if spec.get("fill_40"):
        _fill_40(team)
    if spec.get("pre_il"):
        models.InjuredListStint.objects.create(
            player=player,
            team=team,
            length="7",
            placed_on=timezone.localdate(),
            active_stint=True,
        )
    if spec.get("pre_rl"):
        models.RestrictedListStint.objects.create(
            player=player,
            team=team,
            rl_type="PED",
            placed_on=timezone.localdate(),
            active_stint=True,
        )

    expected_team_id = player.team_id
    terms = {"years": 1, "total": 720000} if spec.get("contract") or kind["requires_contract"] else None
    if spec.get("trade"):
        assets = [
            {
                "asset_type": "cash",
                "amount": 500000,
                "raw_label": "Cash Reserves",
                "from_team": team,
                "to_team": ctx["other_team"],
            }
        ]
    else:
        assets = [{"asset_type": "player", "player": player}]

    proposal = create_proposal(
        user=ctx["actor"],
        team=team,
        code=code,
        assets=assets,
        counterparty_team=ctx["other_team"] if spec.get("trade") else None,
        notes=spec.get("notes") or "",
        contract_terms=terms,
        rl_type=spec.get("rl_type") or "",
        limbo_reason=spec.get("limbo_reason") or "",
    )
    opened = proposal.get_status_display()
    if spec.get("trade"):
        _expect(proposal.status == models.TransactionProposal.AWAITING, "A trade did not wait for the other club.")
        agree(ctx["other_user"], proposal)
    else:
        _expect(proposal.status == models.TransactionProposal.PROPOSED, f"Opened as {opened}.")
    if kind["requires_contract"]:
        _expect(bool(proposal.contract_terms), "Contract terms were not stored.")

    execute_proposal(ctx["actor"], proposal)
    proposal.refresh_from_db()
    player.refresh_from_db()
    _expect(proposal.status == models.TransactionProposal.EXECUTED, "The filing did not post.")
    _expect(player.team_id == expected_team_id, "The player was moved. Directors still apply roster effects.")
    ledger = models.Transaction.objects.get(proposal=proposal)
    _expect(ledger.transaction_type_id and ledger.transaction_type.code == code, "The ledger type code does not match.")
    _expect(
        ledger.raw_transaction_type == kind["label"],
        f"The ledger label is {ledger.raw_transaction_type!r}. The catalog name is {kind['label']!r}.",
    )
    _side_effects(proposal, player, code)

    sentence = f"Opened as {opened}. Posted to the ledger as \"{kind['label']}\"."
    if spec.get("trade"):
        sentence += " The other club agreed before it posted."
    sentence += " No roster row was changed."
    extra = _side_effect_sentence(code)
    if extra:
        sentence += " " + extra
    return sentence


def _side_effects(proposal, player, code):
    if code in IL_OPEN:
        stint = proposal.il_stints.get()
        _expect(stint.length == IL_OPEN[code], "The injured-list stint has the wrong length.")
    elif code == "il_activate":
        stint = player.il_stints.get()
        _expect(not stint.active_stint, "The injured-list stint stayed open.")
    elif code == "il_move":
        _expect(not proposal.il_stints.exists(), "Moving a player between lists opened a new stint.")
    elif code == "in_limbo":
        span = proposal.limbo.deadline - proposal.limbo.placed_on
        _expect(span == datetime.timedelta(days=7), "In limbo did not get a seven-day deadline.")
        _expect(proposal.limbo.reason == "pending_trade", "The limbo reason was not stored.")
    elif code == "restricted_place":
        from npl.transactions.catalog import rl_rules

        stint = proposal.restricted_stints.get()
        rules = rl_rules("PED")
        _expect(stint.rl_type == "PED", "The restricted-list type was not PED.")
        _expect(stint.counts_against_40 == rules["counts_against_40"], "PED roster flags were not applied.")
        _expect(stint.accrues_salary == rules["accrues_salary"], "PED salary flags were not applied.")
    elif code == "restricted_activate":
        stint = player.restricted_stints.get()
        _expect(not stint.active_stint, "The restricted-list stint stayed open.")
    elif code in WAIVER_TYPES:
        waiver = proposal.waiver
        _expect(waiver.waiver_type == WAIVER_TYPES[code], "The waiver type was wrong.")
        _expect(waiver.status == models.Waiver.OPEN, "The waiver was not opened.")
        _expect(waiver.player_id == player.mlb_id, "The waiver is for a different player.")


def _side_effect_sentence(code):
    if code in IL_OPEN:
        return "An injured-list stint was recorded."
    if code == "il_activate":
        return "The open injured-list stint was closed."
    if code == "in_limbo":
        return "The deadline is seven days."
    if code == "restricted_place":
        return "A PED stint was recorded."
    if code == "restricted_activate":
        return "The open restricted-list stint was closed."
    if code in WAIVER_TYPES:
        return "Waivers were opened on the player."
    return ""


def _file_piece(ctx, piece):
    ctx["season"].refresh_from_db()
    ctx["season"].phase = models.Season.REGULAR
    ctx["season"].save(update_fields=["phase", "last_modified"])
    cells = piece.get("cells") or []
    payload = parse_transaction_row(cells) if len(cells) >= 6 else None
    asset = {
        "raw_label": piece["label"],
        "from_team": ctx["team"],
        "to_team": ctx["other_team"],
    }
    amount = payload.get("cash_considerations") if payload else None
    if amount:
        asset["amount"] = amount
    proposal = create_proposal(
        user=ctx["actor"],
        team=ctx["team"],
        code="trade",
        counterparty_team=ctx["other_team"],
        assets=[asset],
    )
    stored = proposal.assets.get()
    _expect(stored.asset_type == piece["asset_type"], f"Stored as {stored.asset_type}, expected {piece['asset_type']}.")
    _expect(stored.qualifier == piece["qualifier"], "The draft-pick qualifier was wrong.")
    if amount:
        _expect(stored.amount == amount, "The dollar amount on the sheet was not stored.")
    label = ASSET_LABELS.get(piece["asset_type"], piece["asset_type"])
    sentence = f"A trade of \"{piece['label']}\" was stored as {label}."
    if piece["qualifier"] == "rule5":
        sentence += " It is a Rule 5 pick."
    elif piece["qualifier"] == "rule4":
        sentence += " It is a Rule 4 pick."
    if amount:
        sentence += f" The amount is ${amount:,}."
    return sentence


def _reset_player(player, team, roster):
    player.team = team
    player.options = 2
    for field in ROSTER_FIELDS:
        setattr(player, field, False)
    for field, value in (roster or {}).items():
        setattr(player, field, value)
    player.save()


def _fill_40(team):
    have = models.Player.objects.filter(team=team, roster_40man=True).count()
    for index in range(40 - have):
        models.Player.objects.create(
            mlb_id=f"npl-audit-roster-{team.id}-{index}",
            name=f"Roster {index}",
            first_name="Roster",
            last_name=str(index),
            team=team,
            roster_40man=True,
            options=2,
        )
