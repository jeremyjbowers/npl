from googleapiclient.discovery import build
from google.oauth2 import service_account

import os
import datetime
import warnings

import gspread
import json
from nameparser import HumanName

import base64

from npl import models


def is_player(row):
    if row != []:
        if row[0].strip() in ["-", "1"]:
            return True
    return False


def get_timestamp():
    current_time = datetime.datetime.now()  
    stamp = current_time.timestamp()
    stamp = f"{stamp}".split('.')[0]
    return int(stamp)

def get_current_season():
    return get_mlb_season(datetime.datetime.today())

def get_mlb_season(date):
    if date.month >= 11:
        return int(date.year) + 1
    return date.year

def division_label(team):
    """Nav and homepage heading, e.g. 'AL East'."""
    league = ""
    if team.league_id and team.league and team.league.name:
        name = team.league.name
        if "American" in name or name.upper() == "AL":
            league = "AL"
        elif "National" in name or name.upper() == "NL":
            league = "NL"
        else:
            league = name
    division = team.division.name if team.division_id and team.division and team.division.name else "Unassigned"
    if league:
        return f"{league} {division}"
    return division


def build_context(request, *, with_teams=True, with_owners=False):
    """Shared page context.

    HTML pages need the club list for the nav. JSON endpoints pass
    with_teams=False and skip that query. Owner lookup is a single
    indexed read; a signed-in user with no club still gets a page.
    """
    context = {}

    queries_without_page = dict(request.GET)
    queries_without_page.pop("page", None)
    context["q_string"] = "&".join(
        ["%s=%s" % (k, v[-1]) for k, v in queries_without_page.items()]
    )

    context["owner"] = None
    context["owner_team"] = None
    if request.user.is_authenticated:
        owner = models.Owner.objects.filter(user_id=request.user.pk).first()
        context["owner"] = owner
        if owner:
            context["owner_team"] = (
                models.Team.objects.filter(owners=owner)
                .select_related("league", "division")
                .first()
            )

    context["all_teams"] = []
    if with_teams:
        teams = models.Team.objects.select_related("league", "division").order_by(
            "league__name", "division__name", "abbreviation", "short_name"
        )
        if with_owners:
            teams = teams.prefetch_related("owners")
        context["all_teams"] = list(teams)
        for team in context["all_teams"]:
            team.division_label = division_label(team)

    return context


def attach_position_counts(teams):
    """One grouped query for the homepage roster tallies."""
    from django.db.models import Count

    from npl.rosters import position_bucket

    team_ids = [team.id for team in teams]
    tallies = {team.id: {"C": 0, "IF": 0, "OF": 0, "P": 0, "UT": 0, "total": 0} for team in teams}
    if not team_ids:
        return teams

    rows = (
        models.Player.objects.filter(team_id__in=team_ids)
        .values("team_id", "simple_position")
        .annotate(n=Count("pk"))
    )
    for row in rows:
        bucket = tallies.get(row["team_id"])
        if bucket is None:
            continue
        key = position_bucket(row["simple_position"])
        bucket[key] += row["n"]
        bucket["total"] += row["n"]

    for team in teams:
        team.pos_counts = tallies.get(team.id, {"C": 0, "IF": 0, "OF": 0, "P": 0, "UT": 0, "total": 0})
    return teams

def to_bool(bool_string):
    if isinstance(bool_string, str):
        if bool_string.strip().lower() in ['y', 'yes', 'true', 't']:
            return True
        return False
    return bool_string

def dollars_to_ints(num_string):
    payload = None
    try:
        if "$" in num_string:
            num_string = num_string.replace('$', '')
        if "," in num_string:
            num_string = num_string.replace(',', '')
        if "." in num_string:
            num_string = num_string.split('.')[0]
        
        payload = int(num_string)

    except:
        pass

    return payload

def format_player_row(row, team, player_dict):
    player_dict['team'] = team

    raw_name = row[1].strip()
    if "Junior" in raw_name:
        raw_name.replace("Junior", "JuniorNAME")
    
    player_dict['raw_name'] = raw_name

    parsed_name = HumanName(raw_name)

    player_dict['first_name'] = parsed_name.first
    if parsed_name.middle:
        player_dict['first_name'] += f" {parsed_name.middle}"

    player_dict['last_name'] = parsed_name.last
    if parsed_name.suffix:
        player_dict['last_name'] += f" {parsed_name.suffix}"

    player_dict['scoresheet_id'] = None
    try:
        player_dict['scoresheet_id'] = int(row[2])
    except:
        pass

    player_dict['mlb_id'] = None
    try:
        player_dict['mlb_id'] = int(row[3])
    except:
        pass

    player_dict['position'] = row[4].strip()
    player_dict['mlb_org'] = row[5].strip()
    
    player_dict['mls_time'] = 0.0
    player_dict['mls_year'] = None
    player_dict['options'] = 0
    player_dict['status'] = None

    if "." in row[6]:
        player_dict['mls_time'] = float(row[6])
        try:
            options_str = row[7].replace('$', '').strip()
            if options_str:
                player_dict['options'] = int(options_str)
        except (ValueError, IndexError, AttributeError):
            pass  # Keep default value of 0

        if len(row) > 8:
            player_dict['status'] = row[8].lower()

    else:
        if row[6].strip() == "":
            row[6] = None
        else:
            player_dict['mls_year'] = int(row[6])

    return player_dict


def get_google_creds(scopes):
    # Suppress RSA keyfile warning - the library auto-corrects malformed keys
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*malformed keyfile.*", category=UserWarning)
        
        if os.environ.get("B64_GOOGLE", None):
            service_account_creds = base64.b64decode(os.environ.get("B64_GOOGLE", None))

            service_account_info = json.loads(service_account_creds)

            creds = service_account.Credentials.from_service_account_info(
                info=service_account_info, scopes=scopes
            )
        else:
            creds = service_account.Credentials.from_service_account_file(filename="credentials.json", scopes=scopes)
    return creds


def write_sheet(sheet_id, sheet_range, data):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = get_google_creds(SCOPES)

    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)

    first_sheet = sheet.get_worksheet(0)

    first_sheet.update(sheet_range, data)


def get_sheet(sheet_id, sheet_range, value_cutoff=None):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    creds = get_google_creds(SCOPES)

    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
    values = result.get("values", None)

    if values:
        return values

def kill_curly(s):
    if isinstance(s, str):
        return s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return s

# covered
def str_to_bool(possible_bool):
    if isinstance(possible_bool, str):
        if possible_bool.lower() in ["y", "yes", "t", "true"]:
            return True
        if possible_bool.lower() in ["n", "no", "f", "false"]:
            return False
    return None


def int_or_none(possible_int):
    if isinstance(possible_int, int):
        return possible_int
    try:
        return to_int(possible_int)
    except:
        pass
    return None


def is_even(possible_int):
    possible_int = int_or_none(possible_int)
    if possible_int:
        if possible_int == 0:
            return True
        if possible_int % 2 == 0:
            return True
    return False

def to_int(might_int, default=None):
    if type(might_int) is int:
        return might_int

    if type(might_int) is str:
        try:
            return int(might_int.strip().replace("\xa0", ""))
        except:
            pass

    try:
        return int(might_int)
    except:
        pass

    if default:
        return default

    return None


def to_float(might_float, default=None):
    try:
        return float(might_float)
    except:
        pass

    return default