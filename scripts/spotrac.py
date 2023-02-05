import datetime
import requests
import ujson as json
import csv
from bs4 import BeautifulSoup


URL_BASE = f"https://www.spotrac.com/mlb/international/"

years = range(2016, datetime.datetime.today().year+1)

payload = []

for y in years:
    r = requests.get(f"{URL_BASE}{y}")
    soup = BeautifulSoup(r.content, 'html.parser')
    rows = soup.select('div.teams > table.datatable > tbody > tr')

    for row in rows:
        cells = row.select('td')
        player_dict = {}
        player_dict['year'] = y
        player_dict['name'] = cells[0].select('a')[0].text.strip()
        player_dict['spotrac_url'] = cells[0].select('a')[0].attrs['href']
        player_dict['spotrac_id'] = player_dict['spotrac_url'].split('/player/')[1].replace('/', '').strip()
        player_dict['team'] = cells[3].text.strip()
        player_dict['bonus'] = 0
        player_dict['position'] = cells[1].text.strip()
        player_dict['country'] = cells[2].text.strip()
        player_dict['mlb_id'] = None
        player_dict['birthdate'] = None
        
        if cells[4].text.strip() != '':
            player_dict['bonus'] = int(cells[4].text.strip().replace('$', '').replace(',', ''))

        payload.append(player_dict)

with open('data/international.json', 'w') as writefile:
    writefile.write(json.dumps(payload))