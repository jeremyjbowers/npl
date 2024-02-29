from googleapiclient.discovery import build
from google.oauth2 import service_account

import os
import datetime

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

def get_mlb_season(date):
    if date.month >= 11:
        return int(date.year) + 1
    return date.year

def build_context(request):
    context = {}

    # to build the nav
    context["all_teams"] = models.Team.objects.all().order_by('league', 'division', 'name')

    # for search
    queries_without_page = dict(request.GET)
    if queries_without_page.get("page", None):
        del queries_without_page["page"]
    context["q_string"] = "&".join(
        ["%s=%s" % (k, v[-1]) for k, v in queries_without_page.items()]
    )

    # add the owner to the page
    context["owner"] = None
    if request.user.is_authenticated:
        try:
            owner = models.Owner.objects.get(user=request.user)
            context["owner"] = owner
            context['owner_team'] = models.Team.objects.get(owners=owner)
        except models.Owner.DoesNotExist:
            pass

    return context

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
    player_dict['options'] = None
    player_dict['status'] = None

    if "." in row[6]:
        player_dict['mls_time'] = float(row[6])
        player_dict['options'] = int(row[7].replace('$', ''))

        if len(row) > 8:
            player_dict['status'] = row[8].lower()

    else:
        if row[6].strip() == "":
            row[6] = None
        else:
            player_dict['mls_year'] = int(row[6])

    return player_dict


def get_google_creds(scopes):
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