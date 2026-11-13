"""Turn one simulated game into the box score the site keeps.

The engine returns plate appearances. This adds them up. Earned runs are the
runs charged to the pitcher: the engine does not separate unearned runs.
"""

AT_BAT_SKIP = {"walk", "hit_by_pitch", "intentional_walk", "bunt_sacrifice", "sacrifice_fly"}
HITS = {"single", "double", "triple", "home_run", "bunt_single"}
STARTER_OUTS = 15


def baseball_ip(outs):
    """Outs the way a box score writes them. 20 outs is 6.2."""
    return f"{outs // 3}.{outs % 3}"


def _change(result):
    return result.get("change") or {}


def _scored_runner(event):
    if not isinstance(event, dict):
        return None
    body = event.get("scored") or event.get("Scored")
    if isinstance(body, dict):
        return body.get("runner")
    return None


def _row(store, key, blank):
    row = store.get(key)
    if row is None:
        row = blank()
        store[key] = row
    return row


def box_from_results(results, names, line_score, score):
    """
    ``names`` maps a player id to a display name. ``line_score`` is
    ``{"away": [...], "home": [...]}`` and ``score`` is ``{"away": n, "home": n}``.
    """
    batting = {"away": {}, "home": {}}
    pitching = {"away": {}, "home": {}}
    order = {"away": [], "home": []}
    pitch_order = {"away": [], "home": []}
    half = "top"
    outs = 0
    inning = 1
    running = {"away": 0, "home": 0}
    current = {"away": None, "home": None}
    starter = {"away": None, "home": None}
    entered = {}
    lead_pitcher = {"away": None, "home": None}
    blown = {"away": None, "home": None}
    done = False

    def batter_row(side, player_id):
        def blank():
            order[side].append(player_id)
            return {
                "player_id": player_id,
                "name": names.get(player_id) or player_id,
                "pa": 0,
                "ab": 0,
                "r": 0,
                "h": 0,
                "hr": 0,
                "2b": 0,
                "3b": 0,
                "rbi": 0,
                "bb": 0,
                "k": 0,
                "hbp": 0,
                "sf": 0,
            }
        return _row(batting[side], player_id, blank)

    def pitcher_row(side, player_id):
        def blank():
            pitch_order[side].append(player_id)
            return {
                "player_id": player_id,
                "name": names.get(player_id) or player_id,
                "outs": 0,
                "h": 0,
                "r": 0,
                "er": 0,
                "bb": 0,
                "k": 0,
                "hr": 0,
                "bf": 0,
            }
        return _row(pitching[side], player_id, blank)

    for result in results:
        if done:
            break
        batting_side = "away" if half == "top" else "home"
        fielding_side = "home" if batting_side == "away" else "away"
        outcome = result.get("outcome") or ""
        change = _change(result)
        batter_id = result.get("batter_id")
        pitcher_id = result.get("pitcher_id")
        completed = result.get("batter_completed", True)
        runs = int(change.get("runs_scored") or 0)
        added = int(change.get("outs_added") or 0)

        if pitcher_id and current[fielding_side] != pitcher_id:
            current[fielding_side] = pitcher_id
            if starter[fielding_side] is None:
                starter[fielding_side] = pitcher_id
            if pitcher_id not in entered:
                entered[pitcher_id] = running[fielding_side] - running[batting_side]

        if completed and batter_id:
            row = batter_row(batting_side, batter_id)
            row["pa"] += 1
            if outcome not in AT_BAT_SKIP:
                row["ab"] += 1
            if outcome in HITS:
                row["h"] += 1
            if outcome == "home_run":
                row["hr"] += 1
            if outcome == "double":
                row["2b"] += 1
            if outcome == "triple":
                row["3b"] += 1
            if outcome in ("walk", "intentional_walk"):
                row["bb"] += 1
            if outcome == "strikeout":
                row["k"] += 1
            if outcome == "hit_by_pitch":
                row["hbp"] += 1
            if outcome == "sacrifice_fly":
                row["sf"] += 1
            if outcome != "caught_stealing":
                row["rbi"] += runs

        scored = []
        for event in result.get("baserunning") or []:
            runner = _scored_runner(event)
            if not runner:
                continue
            scored.append(runner)
            batter_row(batting_side, runner)["r"] += 1
        if outcome == "home_run" and batter_id and batter_id not in scored:
            batter_row(batting_side, batter_id)["r"] += 1

        if pitcher_id:
            row = pitcher_row(fielding_side, pitcher_id)
            row["outs"] += added
            row["r"] += runs
            row["er"] += runs
            if completed:
                row["bf"] += 1
                if outcome in HITS:
                    row["h"] += 1
                if outcome == "home_run":
                    row["hr"] += 1
                if outcome in ("walk", "intentional_walk"):
                    row["bb"] += 1
                if outcome == "strikeout":
                    row["k"] += 1

        before = dict(running)
        running[batting_side] += runs
        if running["away"] != running["home"]:
            leader = "away" if running["away"] > running["home"] else "home"
            trailer = "home" if leader == "away" else "away"
            if before[leader] <= before[trailer] and running[leader] > running[trailer]:
                lead_pitcher[leader] = current[leader]
                blown[trailer] = pitcher_id

        outs += added
        if outs >= 3:
            outs = 0
            if half == "top":
                if inning >= 9 and running["home"] > running["away"]:
                    done = True
                else:
                    half = "bottom"
            else:
                if inning >= 9 and running["home"] != running["away"]:
                    done = True
                else:
                    inning += 1
                    half = "top"

    winner = None
    if running["away"] > running["home"]:
        winner = "away"
    elif running["home"] > running["away"]:
        winner = "home"
    win_id = loss_id = save_id = None
    if winner:
        loser = "home" if winner == "away" else "away"
        win_id = _winning_pitcher(winner, starter[winner], pitching[winner], lead_pitcher[winner])
        loss_id = blown[loser] or starter[loser]
        finisher = current[winner]
        lead = entered.get(finisher)
        if finisher and finisher != win_id and lead is not None and 0 < lead <= 3:
            save_id = finisher

    def pitching_lines(side):
        lines = []
        for player_id in pitch_order[side]:
            row = dict(pitching[side][player_id])
            row["ip"] = baseball_ip(row["outs"])
            lines.append(row)
        return lines

    return {
        "line": {"away": list(line_score.get("away") or []), "home": list(line_score.get("home") or [])},
        "away": {"batting": [batting["away"][pid] for pid in order["away"]], "pitching": pitching_lines("away")},
        "home": {"batting": [batting["home"][pid] for pid in order["home"]], "pitching": pitching_lines("home")},
        "score": {"away": score.get("away", running["away"]), "home": score.get("home", running["home"])},
        "win_id": win_id,
        "loss_id": loss_id,
        "save_id": save_id,
        "win": names.get(win_id) if win_id else None,
        "loss": names.get(loss_id) if loss_id else None,
        "save": names.get(save_id) if save_id else None,
    }


def _winning_pitcher(side, starter_id, rows, lead_pitcher):
    if not rows:
        return None
    starter_outs = rows.get(starter_id, {}).get("outs", 0) if starter_id else 0
    relievers = {
        player_id: row["outs"]
        for player_id, row in rows.items()
        if player_id != starter_id and row["outs"] > 0
    }
    if starter_id and starter_outs >= STARTER_OUTS and (lead_pitcher in (None, starter_id) or not relievers):
        return starter_id
    if lead_pitcher and lead_pitcher != starter_id and rows.get(lead_pitcher, {}).get("outs", 0) > 0:
        return lead_pitcher
    if relievers:
        return max(relievers, key=relievers.get)
    return starter_id or next(iter(rows))
