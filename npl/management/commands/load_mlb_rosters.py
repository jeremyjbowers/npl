import json
import shutil
import subprocess
import time

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests

from npl import models

# MLB's edge returns 406 to the default requests fingerprint from App Platform.
# A browser Accept header, then curl, is what gets a JSON body back.
MLB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.mlb.com/",
    "Accept-Encoding": "gzip, deflate",
}


class _CurlResponse:
    def __init__(self, status_code, content, url):
        self.status_code = status_code
        self.content = content
        self.url = url
        self.text = content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {self.url}", response=self)


def _curl_get(url):
    if shutil.which("curl") is None:
        return None
    completed = subprocess.run(
        [
            "curl", "-sS", "-L", "--http1.1", "--noproxy", "*",
            "-A", MLB_HEADERS["User-Agent"],
            "-H", "Accept: */*",
            "-H", "Referer: https://www.mlb.com/",
            "-w", "\n%{http_code}",
            url,
        ],
        capture_output=True,
        timeout=40,
    )
    raw = completed.stdout
    if not raw:
        return None
    body, _, status = raw.rpartition(b"\n")
    try:
        code = int(status.strip() or b"0")
    except ValueError:
        return None
    return _CurlResponse(code, body, url)


def mlb_get(url, params=None):
    prepared = requests.Request("GET", url, params=params).prepare()
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        response = session.get(url, params=params, headers=MLB_HEADERS, timeout=30)
    except requests.RequestException:
        response = None
    if response is not None and response.status_code == 200:
        return response
    curled = _curl_get(prepared.url)
    if curled is not None and (response is None or curled.status_code == 200 or response.status_code != 200):
        if curled.status_code == 200 or response is None:
            return curled
    return response if response is not None else curled


def fetch_teams(season):
    sports = (1, 11, 12, 13, 14, 15, 16)
    combined = mlb_get(
        "https://statsapi.mlb.com/api/v1/teams",
        params={"season": season, "sportId": ",".join(str(sport) for sport in sports)},
    )
    if combined is not None and combined.status_code == 200:
        return combined.json().get("teams") or []

    teams = []
    errors = []
    for sport in sports:
        response = mlb_get(
            "https://statsapi.mlb.com/api/v1/teams",
            params={"season": season, "sportId": sport},
        )
        if response is None or response.status_code != 200:
            status = getattr(response, "status_code", "no response")
            errors.append(f"sport {sport}: {status}")
            continue
        teams.extend(response.json().get("teams") or [])
    if not teams:
        detail = "; ".join(errors) or "no response"
        raise CommandError(f"MLB rejected the team list ({detail}).")
    return teams


def fetch_roster(team_id, roster_types):
    """Return the first roster payload MLB will serve for this club.

    fullSeason is the affiliate roster, but MLB answers 406 for that type
    often enough that the call has to fall through to another type and retry.
    """
    last_status = None
    for roster_type in roster_types:
        url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster/{roster_type}"
        for attempt in range(3):
            response = mlb_get(url)
            if response is None:
                last_status = "no response"
                time.sleep(1 + attempt)
                continue
            last_status = response.status_code
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if isinstance(payload, dict):
                    payload["_roster_type"] = roster_type
                    return payload
            if response.status_code in (406, 429, 500, 502, 503):
                time.sleep(0.4 * (attempt + 1))
                continue
            break
    return {"_error": last_status}


class Command(BaseCommand):
    mlb_lookup = {
        "108": "LAA",
        "109": "AZ",
        "110": "BAL",
        "111": "BOS",
        "112": "CHC",
        "113": "CIN",
        "114": "CLE",
        "115": "COL",
        "116": "DET",
        "117": "HOU",
        "118": "KC",
        "119": "LAD",
        "120": "WSH",
        "121": "NYM",
        "133": "ATH",
        "134": "PIT",
        "135": "SD",
        "136": "SEA",
        "137": "SF",
        "138": "STL",
        "139": "TB",
        "140": "TEX",
        "141": "TOR",
        "142": "MIN",
        "143": "PHI",
        "144": "ATL",
        "145": "CWS",
        "146": "MIA",
        "147": "NYY",
        "158": "MIL",
    }
    
    def get_rosters(self):
        models.Player.objects.all().update(roster_status="MINORS")
        season = getattr(settings, "LEAGUE_YEAR", 2026)
        team_list = fetch_teams(season)
        self.saved = 0
        self.skipped = []

        for sport_id in (1, 11, 12, 13, 14, 15, 16):
            for team in team_list:
                if team["sport"]["id"] == sport_id:
                    self.parse_players(team)

        self.stdout.write(f"Saved {self.saved} player rows from the {season} rosters.")
        if self.skipped:
            self.stdout.write(f"Skipped {len(self.skipped)} clubs: {', '.join(self.skipped[:12])}")
        if self.saved == 0:
            raise CommandError("MLB returned no rosters. The 406 responses were rejections, not empty clubs.")

    def parse_players(self, t):
        # 40-man is the MLB roster. Affiliate pages are the full-season roster.
        roster_types = ("40Man", "active") if t["sport"]["id"] == 1 else ("fullSeason", "active", "fullRoster")
        tr = fetch_roster(t["id"], roster_types)

        if t["sport"]["id"] != 1:
            try:
                mlb_team = self.mlb_lookup[str(t["parentOrgId"])]
            except Exception:
                mlb_team = None
                self.stdout.write(f"No parent club for {t.get('name')} ({t.get('id')})")
        else:
            mlb_team = t["abbreviation"]
        roster = tr.get("roster")
        if roster is None:
            self.skipped.append(f"{t.get('name')} ({tr.get('_error')})")
            return
        if not roster:
            return
        else:
            for p in tr['roster']:
                player_dict = {}
                player_dict['mlb_id'] = p['person']['id']
                player_dict['name'] = p['person']['fullName']
                player_dict['position'] = p['position']['abbreviation']
                player_dict['mlb_org'] = mlb_team

                if "injured" in p['status']['description'].lower():
                    if "7" in p['status']['description']:
                        player_dict['roster_status'] = "IL-7"
                    if "10" in p['status']['description']:
                        player_dict['roster_status'] = "IL-10"
                    if "15" in p['status']['description']:
                        player_dict['roster_status'] = "IL-15"
                    if "60" in p['status']['description']:
                        player_dict['roster_status'] = "IL-60"

                if t['sport']['id'] == 1:
                    if 'active' in p['status']['description'].lower():
                        player_dict['roster_status'] = "MLB"

                try:
                    obj = models.Player.objects.get(mlb_id=player_dict['mlb_id'])
                
                except models.Player.DoesNotExist:
                    obj = models.Player()
                
                for k,v in player_dict.items():
                    setattr(obj, k, v)

                obj.save()
                self.saved += 1

    def fix_bad_player_ids(self):
        bad_ids = models.Player.objects.filter(mlb_id__icontains="/")
        bad_ids.delete()
        bad_ids = models.Player.objects.filter(mlb_id__icontains="/")

    def handle(self, *args, **options):
        self.fix_bad_player_ids()
        self.get_rosters()
