import datetime
import requests
import ujson as json
import csv
from bs4 import BeautifulSoup

import time

for year in ['2024', '2023', '2022', '2021', '2019', '2018', '2017', '2016']


# URL_BASE = f"https://www.spotrac.com/mlb/international/_year/"

# payload = []

# r = requests.get(f"{URL_BASE}2025")
# soup = BeautifulSoup(r.content, 'html.parser')
# rows = soup.select('div#table-wrapper table#table > tbody > tr')

# for row in rows:
#     cells = row.select('td')
#     player_dict = {}
#     player_dict['year'] = 2025
#     player_dict['name'] = cells[0].select('a')[0].text.strip()
#     player_dict['spotrac_url'] = cells[0].select('a')[0].attrs['href']
#     player_dict['spotrac_id'] = player_dict['spotrac_url'].split('/player/')[1].replace('/', '').strip()
#     player_dict['team'] = cells[3].text.strip()
#     player_dict['bonus'] = 0
#     player_dict['position'] = cells[1].text.strip()
#     player_dict['country'] = cells[2].text.strip()
#     player_dict['mlb_id'] = None
#     player_dict['birthdate'] = None
    
#     if cells[4].text.strip().lower() not in ['', 'n/a']:
#         player_dict['bonus'] = int(cells[4].text.strip().replace('$', '').replace(',', ''))

#     search_url = f"https://statsapi.mlb.com/api/v1/people/search?names={player_dict['name']}&sportIds=11,12,13,14,15,5442,16&active=true&hydrate=currentTeam,team"
#     print(search_url)

#     rmlb = requests.get(search_url, timeout=5)

#     results = rmlb.json().get('people', None)

#     if len(results) == 1:
#         p = results[0]
#         player_dict['mlb_id'] = p['id']
#         player_dict['birthdate'] = p['birthDate']

#     payload.append(player_dict)
#     time.sleep(2)

# with open('international_2025.json', 'w') as writefile:
#     writefile.write(json.dumps(payload))

with open('international_2025.json', 'r') as readfile:
    players = json.loads(readfile.read())
    fieldnames = players[0].keys()

    with open('international_2025.csv', 'w') as writefile:
        writer = csv.DictWriter(writefile, fieldnames=fieldnames)
        writer.writeheader()
        for p in players:
            writer.writerow(p)