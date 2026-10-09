"""Load roster tabs and the Team Owners sheet into the database.

The workbook is the source of truth for this import. Once it is loaded, the
site keeps the teams, MLB IDs, contracts, carried salary, and owner accounts.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from npl import models
from npl.sheet_parse import (
    parse_owners_sheet,
    parse_team_sheet,
    pretty,
    short_name_from_tab,
)
from users.models import User


TAB_RE = re.compile(
    r'items\.push\(\{name: "(.*?)", pageUrl: ".*?", gid: "(\d+)"'
)
USER_AGENT = {"User-Agent": "npl-roster-loader"}

ROSTER_FLAG_NAMES = (
    "roster_85man",
    "roster_40man",
    "roster_30man",
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
    "roster_owaivers",
    "roster_r5waivers",
    "recall_eligible",
    "activation_eligible",
    "waiver_clear",
    "is_r5",
)


def list_workbook_tabs(sheet_id):
    response = requests.get(
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview",
        headers=USER_AGENT,
        timeout=60,
    )
    response.raise_for_status()
    tabs = []
    for name, gid in TAB_RE.findall(response.text):
        tabs.append({"name": name, "gid": gid})
    if not tabs:
        raise RuntimeError(f"No tabs found for spreadsheet {sheet_id}")
    return tabs


def fetch_tab_rows(sheet_id, gid):
    response = requests.get(
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}",
        headers=USER_AGENT,
        timeout=90,
    )
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def match_team(label, teams):
    """Match an owners-sheet team name to a roster tab."""
    if not label:
        return None
    norm = _normalize(label)
    last = _normalize(label.replace(",", " ").split()[-1]) if label.split() else ""
    exact = [
        team
        for team in teams
        if _normalize(team.full_name) == norm or _normalize(team.short_name) == norm
    ]
    if len(exact) == 1:
        return exact[0]
    by_short = [team for team in teams if last and _normalize(team.short_name) == last]
    if len(by_short) == 1:
        return by_short[0]
    by_last = [
        team
        for team in teams
        if team.full_name and _normalize(team.full_name.replace(",", " ").split()[-1]) == last
    ]
    if len(by_last) == 1:
        return by_last[0]
    return None


def _split_person_name(name):
    name = (name or "").strip()
    if not name:
        return "", ""
    if "," in name:
        last, first = name.split(",", 1)
        return first.strip(), last.strip()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _service_time(value):
    if not value or "." not in value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _league(name):
    if not name:
        return None
    league, _created = models.League.objects.get_or_create(name=name)
    return league


def _division(name, league):
    if not name or league is None:
        return None
    division, _created = models.Division.objects.get_or_create(name=name, league=league)
    return division


def _find_team(sheet_title, full_name):
    short = short_name_from_tab(sheet_title)
    team = models.Team.objects.filter(tab_id=sheet_title).first()
    if team is None and short:
        team = models.Team.objects.filter(short_name__iexact=short).first()
    if team is None and full_name:
        team = models.Team.objects.filter(full_name__iexact=full_name).first()
    if team is None:
        team = models.Team(short_name=short or full_name or sheet_title)
    team.tab_id = sheet_title
    if short:
        team.short_name = short
    if full_name:
        team.full_name = full_name
        if short and team.full_name.lower().endswith(short.lower()):
            team.full_name = team.full_name[: -len(short)] + short
    elif not team.full_name:
        team.full_name = short or sheet_title
    return team


def _replace_contract(player, team, contract):
    models.ContractYear.objects.filter(contract__player=player).delete()
    models.Contract.objects.filter(player=player).delete()
    if not contract:
        return None
    created = models.Contract(
        player=player,
        team=team,
        notes=contract["notes"],
        buyout=contract["buyout"],
        can_buyout=contract["buyout_amount"] is not None,
        total_amount=sum(year["amount"] for year in contract["years"]),
        total_years=len(contract["years"]),
    )
    created.save()
    for year in contract["years"]:
        models.ContractYear.objects.create(
            contract=created,
            year=year["year"],
            amount=year["amount"],
        )
    return created


def _apply_player(team, row):
    player = models.Player.objects.filter(mlb_id=row["mlb_id"]).first()
    if player is None:
        player = models.Player(mlb_id=row["mlb_id"], name=row["raw_name"])
    player.team = team
    player.raw_name = row["raw_name"]
    player.first_name = row["first_name"]
    player.last_name = row["last_name"]
    player.position = row["position"]
    player.mlb_org = row["mlb_org"]
    if row["scoresheet_id"]:
        player.scoresheet_id = row["scoresheet_id"]
    player.mls_time = row["mls_time"]
    player.mls_year = row["mls_year"] or None
    player.service_time = _service_time(row["mls_time"])
    player.options = row["options"]
    player.sta = row["sta"]
    player.status = row["sta"].lower()
    player.npl_status = row["section_label"]
    player.is_r5 = bool(re.search(r"\bR5\b", row["sta"]))
    if "QO" in row["sta"]:
        player.has_been_qo = True
    if row["on_40"]:
        player.has_been_npl40 = True
    player.has_been_rostered = True
    for name in ROSTER_FLAG_NAMES:
        setattr(player, name, False)
    for name, value in row["flags"].items():
        setattr(player, name, value)
    player.is_r5 = bool(re.search(r"\bR5\b", row["sta"]))
    player.save()
    _replace_contract(player, team, row["contract"])
    return player


def _counterparty_team(label):
    if not label:
        return None
    return models.Team.objects.filter(short_name__iexact=label).first()


def _link_player(player_name):
    if not player_name:
        return None
    return models.Player.objects.filter(raw_name__iexact=player_name).first()


@transaction.atomic
def apply_team_sheet(parsed, sheet_title, league_year):
    team = _find_team(sheet_title, parsed["full_name"])
    league = _league(parsed["league"])
    division = _division(parsed["division"], league)
    if league:
        team.league = league
    if division:
        team.division = division
    if parsed["founded"]:
        team.initial_season = parsed["founded"]
    if parsed["farms"]["triple_a"]:
        team.triple_a_name = parsed["farms"]["triple_a"]
    if parsed["farms"]["double_a"]:
        team.double_a_name = parsed["farms"]["double_a"]
    if parsed["farms"]["single_a"]:
        team.single_a_name = parsed["farms"]["single_a"]
    team.save()

    models.TeamLedgerYear.objects.filter(team=team).delete()
    for row in parsed["ledger"]:
        models.TeamLedgerYear.objects.create(team=team, **row)

    models.TeamFinancialLine.objects.filter(team=team).delete()
    for row in parsed["lines"]:
        models.TeamFinancialLine.objects.create(
            team=team,
            year=row["year"],
            section=row["section"],
            kind=row["kind"],
            label=row["label"],
            counterparty=row["counterparty"],
            counterparty_team=_counterparty_team(row["counterparty"]),
            player_name=row["player_name"],
            amount=row["amount"],
            text_value=row["text_value"],
            note=row["note"],
            sort_order=row["sort_order"],
        )

    seen = []
    for row in parsed["players"]:
        player = _apply_player(team, row)
        seen.append(player.mlb_id)
    for line in models.TeamFinancialLine.objects.filter(team=team).exclude(player_name=""):
        line.player = _link_player(line.player_name)
        if line.player_id:
            line.save(update_fields=["player"])

    stale = models.Player.objects.filter(team=team).exclude(mlb_id__in=seen)
    for player in stale:
        for name in ROSTER_FLAG_NAMES:
            setattr(player, name, False)
        player.team = None
        player.npl_status = ""
        player.save()
        models.ContractYear.objects.filter(contract__player=player, contract__team=team).delete()
        models.Contract.objects.filter(player=player, team=team).delete()

    current = next((row for row in parsed["ledger"] if row["year"] == league_year), None)
    if current is None and parsed["ledger"]:
        current = parsed["ledger"][0]
    if current:
        team.contract_salary = current["payroll"]
        team.cap_space = current["available_cap"] if current["available_cap"] is not None else current["cap_space"]
        team.cash = current["cash"] if current["cash"] is not None else current["cash_reserves"]
        team.luxury_cap_space = current["luxury_tax"]
        team.ifa = current["ifa_total"]
        if team.cash is not None and team.cash < 0:
            team.cash_borrowing = abs(team.cash)
        elif team.cash is not None:
            team.cash_borrowing = 0
        carried = [
            line["amount"]
            for line in parsed["lines"]
            if line["kind"] == "carried_salary" and line["year"] == current["year"] and line["amount"] is not None
        ]
        if parsed["saw_payroll_section"]:
            team.carried_salary = sum(carried)
        team.save()

        season, _created = models.Season.objects.get_or_create(year=current["year"])
        team_season = models.TeamSeason.objects.filter(team=team, season=season).first()
        if team_season is None:
            team_season = models.TeamSeason(team=team, season=season)
        team_season.league = team.league
        team_season.division = team.division
        team_season.contract_salary = team.contract_salary
        team_season.carried_salary = team.carried_salary
        team_season.cash_borrowing = team.cash_borrowing
        team_season.cap_space = team.cap_space
        team_season.luxury_cap_space = team.luxury_cap_space
        team_season.cash = team.cash
        team_season.ifa = team.ifa
        team_season.roster_85_man = current["roster_85"]
        team_season.roster_40_man = current["roster_40"]
        team_season.roster_30_man = current["roster_30"]
        team_season.save()

    return {
        "team": team,
        "mlb_ids": seen,
        "unresolved": parsed["unresolved"],
        "managers": parsed["managers"],
    }


def _ensure_user(email, name):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User(email=email)
        user.set_unusable_password()
        user.save()
    first, last = _split_person_name(name)
    if first and not user.first_name:
        user.first_name = first
    if last and not user.last_name:
        user.last_name = last
    user.save()
    return user


def _ensure_owner(person, user):
    owner = None
    if user is not None:
        owner = models.Owner.objects.filter(user=user).first()
    if owner is None and person.get("email"):
        owner = models.Owner.objects.filter(email__iexact=person["email"]).first()
    if owner is None and person.get("name"):
        named = models.Owner.objects.filter(name__iexact=person["name"]).first()
        if named and (named.user_id is None or (user and named.user_id == user.id)):
            owner = named
    if owner is None:
        owner = models.Owner(name=person.get("name") or "")
    if person.get("name"):
        owner.name = person["name"]
    if person.get("email"):
        owner.email = person["email"]
    if person.get("year_joined"):
        owner.year_joined = person["year_joined"]
    for field in ("twitter", "phone", "hometown", "bio"):
        if field in person:
            setattr(owner, field, person.get(field) or "")
    if person.get("title"):
        owner.title = person["title"]
    if user is not None:
        owner.user = user
    owner.save()
    return owner


def apply_owners(people, managers=None):
    """Create owner accounts and attach them to the clubs they run.

    ``managers`` are the general-manager lines from roster tabs. An email on
    a team tab links that person to the club even when the owners-sheet team
    name is stale.
    """
    managers = managers or []
    teams = list(models.Team.objects.all())
    manager_team = {}
    manager_title = {}
    manager_name = {}
    for manager in managers:
        email = (manager.get("email") or "").lower()
        if not email:
            continue
        manager_team[email] = manager.get("team")
        manager_title[email] = manager.get("title") or ""
        manager_name[email] = manager.get("name") or ""

    merged = []
    seen_emails = set()
    for person in people:
        email = (person.get("email") or "").lower()
        row = dict(person)
        row["email"] = email
        if email and email in manager_title and not row.get("title"):
            row["title"] = manager_title[email]
        merged.append(row)
        if email:
            seen_emails.add(email)
    for email, team in manager_team.items():
        if email in seen_emails:
            continue
        merged.append(
            {
                "team_label": "",
                "name": manager_name.get(email, ""),
                "year_joined": None,
                "email": email,
                "twitter": "",
                "phone": "",
                "hometown": "",
                "bio": "",
                "title": manager_title.get(email, ""),
                "team": team,
            }
        )

    owners_for_team = {}
    unmatched = []
    created_users = []
    for person in merged:
        user = _ensure_user(person.get("email"), person.get("name"))
        if user is not None and user.email:
            created_users.append(user.email)
        owner = _ensure_owner(person, user)
        team = person.get("team")
        if team is None:
            team = match_team(person.get("team_label") or "", teams)
        if team is None and person.get("email"):
            team = manager_team.get(person["email"])
        if team is None and person.get("team_label"):
            unmatched.append(person["team_label"])
        if team is not None:
            if not team.full_name or team.full_name == team.short_name:
                label = person.get("team_label") or ""
                if label and match_team(label, [team]) is team:
                    team.full_name = pretty(label)
                    team.save(update_fields=["full_name"])
            owners_for_team.setdefault(team.pk, []).append(owner)
    for team_id, owners in owners_for_team.items():
        team = models.Team.objects.get(pk=team_id)
        team.owners.set(owners)
    for manager in managers:
        team = manager.get("team")
        title = manager.get("title") or ""
        name = manager.get("name") or ""
        if not team or not title or not name:
            continue
        team.owners.filter(name__iexact=name).filter(Q(title__isnull=True) | Q(title="")).update(title=title)
    return {
        "owners": sum(len(rows) for rows in owners_for_team.values()),
        "unmatched_teams": sorted(set(unmatched)),
        "emails": sorted(set(created_users)),
    }


def load_roster_workbook(sheet_id=None, league_sheet_id=None, team_name=None, league_year=None, writer=None):
    sheet_id = sheet_id or settings.ROSTER_SHEET_ID
    league_sheet_id = league_sheet_id or settings.LEAGUE_SHEET_ID
    league_year = league_year or settings.LEAGUE_YEAR
    write = writer or (lambda message: None)
    tabs = list_workbook_tabs(sheet_id)
    managers = []
    seen = {}
    loaded = 0
    for tab in tabs:
        if not short_name_from_tab(tab["name"]):
            continue
        if team_name and team_name.lower() not in tab["name"].lower():
            continue
        rows = fetch_tab_rows(sheet_id, tab["gid"])
        parsed = parse_team_sheet(rows)
        result = apply_team_sheet(parsed, tab["name"], league_year)
        loaded += 1
        team = result["team"]
        write(
            f"{team.short_name}: {len(result['mlb_ids'])} players, "
            f"{team.carried_salary} carried salary, {len(result['unresolved'])} unresolved"
        )
        for item in result["unresolved"]:
            write(f"  unresolved {item['raw_name']}: {item['reason']}")
        for mlb_id in result["mlb_ids"]:
            if mlb_id in seen and seen[mlb_id] != team.short_name:
                write(f"  MLB ID {mlb_id} also appears on {seen[mlb_id]}")
            seen[mlb_id] = team.short_name
        for manager in result["managers"]:
            manager = dict(manager)
            manager["team"] = team
            managers.append(manager)

    owner_tabs = list_workbook_tabs(league_sheet_id)
    owners_tab = next((tab for tab in owner_tabs if tab["name"] == "Team Owners"), None)
    owner_result = {"owners": 0, "unmatched_teams": [], "emails": []}
    if owners_tab:
        people = parse_owners_sheet(fetch_tab_rows(league_sheet_id, owners_tab["gid"]))
        owner_result = apply_owners(people, managers)
        write(
            f"Owners: {len(owner_result['emails'])} accounts, "
            f"unmatched teams: {', '.join(owner_result['unmatched_teams']) or 'none'}"
        )
    else:
        owner_result = apply_owners([], managers)
        write("Team Owners tab was not found. Loaded general managers from roster tabs only.")
    return {"teams": loaded, "owners": owner_result}
