def get_fg_minor_season(season=None, timestamp=None, scriptname=None, hostname=None):

    if not hostname:
        hostname = get_hostname()

    if not scriptname:
        scriptname = get_scriptname()

    if not timestamp:
        timestamp = generate_timestamp()

    if not season:
        season = get_current_season()

    print(f"{timestamp}\t{season}\tget_fg_minor_season")

    headers = {"accept": "application/json"}

    players = {"bat": [], "pit": []}

    for k, v in players.items():
        url = f"https://www.fangraphs.com/api/leaders/minor-league/data?pos=all&level=0&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32,33&stats={k}&qual=0&type=0&team=&season={season}&seasonEnd={season}&org=&ind=0&splitTeam=false"

        print(url)
        r = requests.get(url, verify=False)
        players[k] += r.json()

    for k, v in players.items():
        for player in v:
            fg_id = player["playerids"]
            name = player["PlayerName"]
            p = models.Player.objects.filter(fg_id=fg_id)

            if len(p) == 1:
                obj = p[0]

                stats_dict = {}
                stats_dict["type"] = "minors"
                stats_dict["timestamp"] = timestamp
                stats_dict["level"] = player["aLevel"]
                stats_dict["script"] = scriptname
                stats_dict["host"] = hostname
                stats_dict["year"] = season
                stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}"

                if k == "bat":
                    stats_dict["side"] = "hit"
                    stats_dict["hits"] = to_int(player["H"])
                    stats_dict["2b"] = to_int(player["2B"])
                    stats_dict["3b"] = to_int(player["3B"])
                    stats_dict["hr"] = to_int(player["HR"])
                    stats_dict["sb"] = to_int(player["SB"])
                    stats_dict["runs"] = to_int(player["R"])
                    stats_dict["rbi"] = to_int(player["RBI"])
                    stats_dict["avg"] = to_float(player["AVG"])
                    stats_dict["obp"] = to_float(player["OBP"])
                    stats_dict["slg"] = to_float(player["SLG"])
                    stats_dict["babip"] = to_float(player["BABIP"])
                    stats_dict["wrc_plus"] = to_int(player["wRC+"])
                    stats_dict["plate_appearances"] = to_int(player["PA"])
                    stats_dict["iso"] = to_float(player["ISO"])
                    stats_dict["k_pct"] = to_float(player["K%"], default=0.0) * 100.0
                    stats_dict["bb_pct"] = to_float(player["BB%"], default=0.0) * 100.0
                    stats_dict["woba"] = to_float(player["wOBA"])

                if k == "pit":
                    stats_dict["side"] = "pitch"
                    stats_dict["g"] = to_int(player["G"])
                    stats_dict["gs"] = to_int(player["GS"])
                    stats_dict["k"] = to_int(player["SO"])
                    stats_dict["bb"] = to_int(player["BB"])
                    stats_dict["ha"] = to_int(player["H"])
                    stats_dict["hra"] = to_int(player["HR"])
                    stats_dict["ip"] = to_float(player["IP"])
                    stats_dict["k_9"] = to_float(player["K/9"])
                    stats_dict["bb_9"] = to_float(player["BB/9"])
                    stats_dict["hr_9"] = to_float(player["HR/9"])
                    stats_dict["lob_pct"] = (
                        to_float(player["LOB%"], default=0.0) * 100.0
                    )
                    stats_dict["gb_pct"] = to_float(player["GB%"], default=0.0) * 100.0
                    stats_dict["hr_fb"] = to_float(player["HR/FB"])
                    stats_dict["era"] = to_float(player["ERA"])
                    stats_dict["fip"] = to_float(player["FIP"])
                    stats_dict["xfip"] = to_float(player["xFIP"])

                obj.set_stats(stats_dict)
                obj.save()

                current_dict = stats_dict.copy()
                current_dict["slug"] = "current"

                obj.set_stats(current_dict)
                obj.save()


def get_fg_major_hitter_season(season=None, timestamp=None, scriptname=None, hostname=None):

    if not hostname:
        hostname = get_hostname()

    if not scriptname:
        scriptname = get_scriptname()

    if not timestamp:
        timestamp = generate_timestamp()

    if not season:
        season = get_current_season()

    print(f"{timestamp}\t{season}\tget_fg_major_hitter_season")

    url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=bat&lg=all&qual=0&season={season}&season1={season}&startdate={season}-01-01&enddate={season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C6%2C-1%2C312%2C305%2C309%2C306%2C307%2C308%2C310%2C311%2C-1%2C23%2C315%2C-1%2C38%2C316%2C-1%2C50%2C317%2C7%2C8%2C9%2C10%2C11%2C12%2C13%2C14%2C21%2C23%2C34%2C35%2C37%2C38%2C39%2C40%2C41%2C50%2C52%2C57%2C58%2C61%2C62%2C5&sortdir=desc&sortstat=Events"

    rows = requests.get(url).json()['data']

    for row in rows:
        stats_dict = {}

        stats_dict["year"] = season
        stats_dict["type"] = "majors"
        stats_dict["timestamp"] = timestamp
        stats_dict["level"] = "mlb"
        stats_dict["side"] = "hit"
        stats_dict["script"] = scriptname
        stats_dict["host"] = hostname
        stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}"

        obj = models.Player.objects.filter(
            fg_id=row['playerid']
        )

        if obj.count() > 0:
            obj = obj[0]

            stats_dict["hits"] = to_int(row['H'])
            stats_dict["2b"] = to_int(row['2B'])
            stats_dict["3b"] = to_int(row['3B'])
            stats_dict["hr"] = to_int(row['HR'])
            stats_dict["sb"] = to_int(row['SB'])
            stats_dict["runs"] = to_int(row['R'])
            stats_dict["rbi"] = to_int(row['RBI'])
            stats_dict["wrc_plus"] = to_int(row['wRC+'])
            stats_dict["plate_appearances"] = to_int(row['PA'])
            stats_dict["ab"] = to_int(row['AB'])

            stats_dict["avg"] = to_float(row['AVG'])
            stats_dict["xavg"] = to_float(row['xAVG'])
            stats_dict["obp"] = to_float(row['OBP'])
            stats_dict["slg"] = to_float(row['SLG'])
            stats_dict["xslg"] = to_float(row['xSLG'])
            stats_dict["babip"] = to_float(row['BABIP'])
            stats_dict["iso"] = to_float(row['ISO'])
            stats_dict["k_pct"] = to_float(row['K%'])
            stats_dict["bb_pct"] = to_float(row['BB%'])
            stats_dict["xwoba"] = to_float(row['xwOBA'])

            obj.set_stats(stats_dict)
            obj.mlbam_id = row['xMLBAMID']
            obj.save()

            current_dict = stats_dict.copy()
            current_dict["slug"] = "current"

            obj.set_stats(current_dict)
            obj.save()


def get_fg_major_pitcher_season(season=None, timestamp=None, scriptname=None, hostname=None):

    if not hostname:
        hostname = get_hostname()

    if not scriptname:
        scriptname = get_scriptname()

    if not timestamp:
        timestamp = generate_timestamp()

    if not season:
        season = get_current_season()

    print(f"{timestamp}\t{season}\tget_fg_major_pitcher_season")

    url = f"https://www.fangraphs.com/api/leaders/major-league/data?age=0&pos=all&stats=pit&lg=all&qual=2&season={season}&season1={season}&startdate={season}-01-01&enddate={season}-12-31&month=0&team=0&pageitems=5000&pagenum=1&ind=0&rost=0&players=0&type=c%2C4%2C5%2C11%2C7%2C8%2C13%2C-1%2C24%2C19%2C15%2C18%2C36%2C37%2C40%2C43%2C44%2C48%2C51%2C-1%2C240%2C-1%2C6%2C332%2C45%2C62%2C122%2C-1%2C59%2C17%2C301%2C302%2C303%2C117%2C118%2C119&sortdir=desc&sortstat=SO"

    rows = requests.get(url).json()['data']

    for row in rows:
        stats_dict = {}

        stats_dict["year"] = season
        stats_dict["type"] = "majors"
        stats_dict["timestamp"] = timestamp
        stats_dict["level"] = "mlb"
        stats_dict["side"] = "pitch"
        stats_dict["script"] = scriptname
        stats_dict["host"] = hostname
        stats_dict["slug"] = f"{stats_dict['year']}_{stats_dict['type']}"

        obj = models.Player.objects.filter(
            fg_id=row['playerid']
        )

        if obj.count() > 0:
            obj = obj[0]

            stats_dict["g"] = to_int(row['G'])
            stats_dict["gs"] = to_int(row['GS'])
            stats_dict["k"] = to_int(row['SO'])
            stats_dict["bb"] = to_int(row['BB'])
            stats_dict["ha"] = to_int(row['H'])
            stats_dict["hra"] = to_int(row['HR'])
            stats_dict["ip"] = to_float(row['IP'])
            stats_dict["k_9"] = to_float(row['K/9'])
            stats_dict["bb_9"] = to_float(row['BB/9'])
            stats_dict["hr_9"] = to_float(row['HR/9'])
            stats_dict["lob_pct"] = to_float(row['LOB%'])
            stats_dict["gb_pct"] = to_float(row['GB%'])
            stats_dict["hr_fb"] = to_float(row['HR/FB'])
            stats_dict["era"] = to_float(row['ERA'])
            stats_dict["fip"] = to_float(row['FIP'])
            stats_dict["xfip"] = to_float(row['xFIP'])
            stats_dict["siera"] = to_float(row['SIERA'])
            stats_dict['xERA'] = to_float(row['xERA'])
            stats_dict['sp_stuff'] = to_float(row['sp_stuff'])
            stats_dict['sp_location'] = to_float(row['sp_location'])
            stats_dict['sp_pitching'] = to_float(row['sp_pitching'])
            stats_dict["er"] = to_float(row['ER'])
            stats_dict["k_9+"] = to_int(row['K/9+'])
            stats_dict["bb_9+"] = to_int(row['BB/9+'])
            stats_dict["era-"] = to_int(row['ERA-'])
            stats_dict["fip-"] = to_int(row['FIP-'])
            stats_dict["xfip-"] = to_int(row['xFIP-'])

            obj.set_stats(stats_dict)
            obj.mlbam_id = row['xMLBAMID']
            obj.save()

            current_dict = stats_dict.copy()
            current_dict["slug"] = "current"

            obj.set_stats(current_dict)
            obj.save()