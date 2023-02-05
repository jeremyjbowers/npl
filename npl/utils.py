from googleapiclient.discovery import build
from google.oauth2 import service_account

import os

import gspread
import json
from nameparser import HumanName

import base64

def is_player(row):
    if len(row) > 0:
        if len(row[0].strip()) == 1:
            return True
    return False

def format_player_row(row, team):
    player_dict = {}

    player_dict['npl_team'] = team.split(' #')[0].strip()

    player_dict['is_40man_roster'] = False
    if row[0] == "1":
        player_dict['is_40man_roster'] = True 

    parsed_name = HumanName(row[1].strip())

    player_dict['first'] = parsed_name.first
    if parsed_name.middle:
        player_dict['first'] += f" {parsed_name.middle}"

    player_dict['last'] = parsed_name.last
    if parsed_name.suffix:
        player_dict['last'] += f" {parsed_name.suffix}"

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
    player_dict['mlb_team'] = row[5].strip()
    
    player_dict['mls'] = 0.0
    player_dict['r5_expire'] = None
    player_dict['options'] = None
    player_dict['qo'] = False

    if "." in row[6]:
        player_dict['mls'] = float(row[6])
        player_dict['options'] = int(row[7].replace('$', ''))

        if len(row) > 8:
            if "qo" in row[8].lower():
                player_dict['qo'] = True

    else:
        player_dict['r5_expire'] = int(row[6])

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