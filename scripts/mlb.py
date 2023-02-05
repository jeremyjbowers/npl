import requests
from bs4 import BeautifulSoup
import ujson as json
import csv
from nameparser import HumanName
import time
import os

players = []

with open('data/international_with_birthdates.json', 'r') as readfile:
    players = json.loads(readfile.read())

BASE_URL = "https://yvo49oxzy7-dsn.algolia.net/1/indexes/*/queries?x-algolia-api-key=2305f7af47eda36d30e1fa05f9986e56&x-algolia-application-id=YVO49OXZY7"

for p in players:
    name = p['name']
    data = {}

    data["requests"] = [
        {"indexName":"mlb-players","params":f"query={name}"},
    ]

    headers = {}
    headers['Accept'] = "*/*"
    headers['Accept-Encoding'] = "gzip, deflate, br"
    headers['Accept-Language'] = "en-US,en;q=0.9"
    headers['Connection'] = "keep-alive"
    headers['Content-Length'] = "603"
    headers['Host'] = "yvo49oxzy7-dsn.algolia.net"
    headers['Origin'] = "https://www.mlb.com"
    headers['Sec-Fetch-Dest'] = "empty"
    headers['Sec-Fetch-Mode'] = "cors"
    headers['Sec-Fetch-Site'] = "cross-site"
    headers['User-Agent'] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.70"
    headers['content-type'] = "application/x-www-form-urlencoded"
    headers['sec-ch-ua'] = '"Not_A Brand";v="99", "Microsoft Edge";v="109", "Chromium";v="109"'
    headers['sec-ch-ua-mobile'] = "?0"
    headers['sec-ch-ua-platform'] = '"macOS"'

    filepath = f"data/mlbids/{p['spotrac_id']}.json"

    if not os.path.exists(filepath):
        print(p['name'], p['year'])
        r = requests.post(BASE_URL, headers=headers, data=json.dumps(data))

        results = r.json()['results']
        if len(results[0]['hits']) > 0:
            mlb_id = results[0]['hits'][0]['url'].split('player/')[1].replace('/', '')

            p['mlb_id'] = mlb_id

            with open(filepath, 'w') as writefile:
                writefile.write(json.dumps(p))

            time.sleep(0.5)