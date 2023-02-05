from bs4 import BeautifulSoup
import requests
import ujson as json
import datetime
import time

import os

def main():
    # write_player_json()
    combine_player_json()


def combine_player_json():
    """
    Takes disparate (cached) player data from both
    the original spotrac international file
    and the birthdate-added JSON in the cache directory
    and combines them into a file with birthdates.
    """
    payload = []
    players = []
    
    with open('data/international.json', 'r') as readfile:
        players = json.loads(readfile.read())

    for p in players:
        filepath = f"data/birthdates/{p['spotrac_id']}.json"

        if os.path.exists(filepath):
            with open(filepath, 'r') as readfile:
                player = json.loads(readfile.read())
                payload.append(player)

        else:
            payload.append(p)

    with open('data/international_with_birthdates.json', 'w') as writefile:
        writefile.write(json.dumps(payload))


def write_player_json():
    """
    Combs through the original spotrac international data
    and harvests birthdates from the web, writing the results
    in JSON to a temp file in the data/ directory.
    """
    today = datetime.datetime.today()

    players = []

    with open('data/international.json', 'r') as readfile:
        players = json.loads(readfile.read())

    for p in players:
        filepath = f"data/birthdates/{p['spotrac_id']}.json"

        if not os.path.exists(filepath):
            print(p['name'], p['year'])
            time.sleep(1)
            r = requests.get(p['spotrac_url'])
            soup = BeautifulSoup(r.content, 'html.parser')

            p['birthdate'] = None
            age = None

            try:
                raw_age = soup.select('div#main span.player-item')[2].text.strip()
                if "Age:" in raw_age:
                    age = raw_age.replace('Age:', '').strip()

                if age:
                    years = int(age.split('-')[0].strip())
                    days = int(age.split('-')[1].replace('d', '').strip())

                    days += years*365
                    delta = datetime.timedelta(days=days)
                    birthdate = today - delta
                    year = birthdate.year
                    month = f"{birthdate.month}".zfill(2)
                    day = f"{birthdate.day}".zfill(2)
                    p['birthdate'] = f"{year}-{month}-{day}"
                    
                    with open(filepath, 'w') as writefile:
                        writefile.write(json.dumps(p))
            
            except:
                pass

if __name__ == "__main__":
    main()