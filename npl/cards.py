"""Weekly cards: last year's true talent, plus the usage that updates it.

A card is what the Sunday sim will eventually hand the engine, and what a
manager reads during the week.

Last year's major-league line becomes true talent by pulling BABIP, home-run
rate, and home runs allowed toward the league. Strikeouts and walks stay.
That talent is the prior. It counts as a block of playing time that shrinks
each week, from the whole card in week 1 down to 15 percent in the last week.

Each later week adds the playing time recorded since the previous card. The
new line is the updated true talent. Week 1 folds nothing in, because there
is no current season yet.
"""

WEEKS = 27
PRIOR_FLOOR = 0.15

LEAGUE_BABIP = 0.290
LEAGUE_HR_PA = 0.031
LEAGUE_K_PCT = 22.6
LEAGUE_BB_PCT = 8.4
LEAGUE_HBP_PA = 0.011
LEAGUE_K9 = 8.8
LEAGUE_BB9 = 3.2
LEAGUE_HR9 = 1.2
LEAGUE_H9 = 8.3
FIP_CONSTANT = 3.10
HITTER_REGRESSION_PA = 300
PITCHER_REGRESSION_IP = 60.0

HITTER_KEYS = ("pa", "k", "bb", "hr", "bip", "bip_hits")
PITCHER_KEYS = ("ip", "k", "bb", "hr", "h")


def prior_weight(week, weeks=WEEKS):
    """Share of the card that still comes from last year's true talent."""
    if week < 1 or week > weeks:
        raise ValueError(f"week must be 1..{weeks}")
    if week == 1:
        return 1.0
    raw = 1 - (week - 1) / (weeks - 1)
    return max(PRIOR_FLOOR, raw)


def prior_percent(week):
    return round(prior_weight(week) * 100)


def blend_sentence(week):
    percent = prior_percent(week)
    if week <= 1:
        return "Week 1 has no current season yet, so the card is last year's true talent."
    live = 100 - percent
    return (
        f"This card is {percent}% last year's true talent and {live}% "
        "this season through the previous card."
    )


def _percent(value):
    """Accept 22.5 or 0.225 and return a percent."""
    if value is None:
        return None
    number = float(value)
    if abs(number) <= 1:
        return number * 100
    return number


def empty_hitter():
    return {key: 0.0 for key in HITTER_KEYS}


def empty_pitcher():
    return {key: 0.0 for key in PITCHER_KEYS}


def _add(left, right, keys):
    return {key: float(left.get(key, 0) or 0) + float(right.get(key, 0) or 0) for key in keys}


def _scale(counts, weight, keys):
    return {key: float(counts.get(key, 0) or 0) * weight for key in keys}


def _delta(current, previous, keys):
    usage = {}
    for key in keys:
        usage[key] = max(0.0, float(current.get(key, 0) or 0) - float(previous.get(key, 0) or 0))
    return usage


def hitter_counts(line):
    """Plate-appearance evidence from a season line. Missing luck stats use the league."""
    if not line:
        return empty_hitter()
    plate_appearances = float(line.get("plate_appearances") or line.get("pa") or 0)
    if plate_appearances <= 0:
        return empty_hitter()
    k_pct = _percent(line.get("k_pct"))
    bb_pct = _percent(line.get("bb_pct"))
    strikeouts = (k_pct / 100.0) * plate_appearances if k_pct is not None else (LEAGUE_K_PCT / 100.0) * plate_appearances
    walks = (bb_pct / 100.0) * plate_appearances if bb_pct is not None else (LEAGUE_BB_PCT / 100.0) * plate_appearances
    home_runs = float(line.get("hr") or 0)
    hit_by_pitch = LEAGUE_HBP_PA * plate_appearances
    balls_in_play = max(plate_appearances - strikeouts - walks - home_runs - hit_by_pitch, 0.0)
    babip = line.get("babip")
    hits = LEAGUE_BABIP * balls_in_play if babip is None else float(babip) * balls_in_play
    return {
        "pa": plate_appearances,
        "k": strikeouts,
        "bb": walks,
        "hr": home_runs,
        "bip": balls_in_play,
        "bip_hits": hits,
    }


def regress_hitter(counts):
    """Pull BABIP and home-run rate toward the league. Strikeouts and walks stay."""
    plate_appearances = counts.get("pa") or 0
    if plate_appearances <= 0:
        return dict(counts)
    weight = float(HITTER_REGRESSION_PA)
    home_run_rate = (counts["hr"] + LEAGUE_HR_PA * weight) / (plate_appearances + weight)
    balls_in_play = counts.get("bip") or 0
    if balls_in_play <= 0:
        babip_hits = 0.0
    else:
        babip = (counts["bip_hits"] + LEAGUE_BABIP * weight) / (balls_in_play + weight)
        babip_hits = babip * balls_in_play
    return {
        "pa": plate_appearances,
        "k": counts["k"],
        "bb": counts["bb"],
        "hr": home_run_rate * plate_appearances,
        "bip": balls_in_play,
        "bip_hits": babip_hits,
    }


def hitter_rates(counts):
    plate_appearances = counts.get("pa") or 0
    if plate_appearances <= 0:
        return None
    balls_in_play = counts.get("bip") or 0
    return {
        "pa": round(plate_appearances, 1),
        "k_pct": round(100.0 * counts["k"] / plate_appearances, 1),
        "bb_pct": round(100.0 * counts["bb"] / plate_appearances, 1),
        "hr_pa": round(counts["hr"] / plate_appearances, 4),
        "babip": round(counts["bip_hits"] / balls_in_play, 3) if balls_in_play else None,
    }


def hitter_true_talent(line):
    """Luck-neutral prior from one season."""
    return hitter_rates(regress_hitter(hitter_counts(line)))


def blend_hitter(prior_counts, season_counts, week):
    """
    ``prior_counts`` are already regressed. ``season_counts`` are observed.
    Week 1 ignores the current season.
    """
    live_weight = 0.0 if week <= 1 else 1.0
    mixed = _add(
        _scale(prior_counts, prior_weight(week), HITTER_KEYS),
        _scale(season_counts, live_weight, HITTER_KEYS),
        HITTER_KEYS,
    )
    return hitter_rates(mixed)


def pitcher_counts(line):
    if not line:
        return empty_pitcher()
    innings = float(line.get("ip") or 0)
    if innings <= 0:
        return empty_pitcher()
    strikeouts = line.get("k")
    if strikeouts is None and line.get("k_9") is not None:
        strikeouts = float(line["k_9"]) * innings / 9.0
    walks = line.get("bb")
    if walks is None and line.get("bb_9") is not None:
        walks = float(line["bb_9"]) * innings / 9.0
    home_runs = line.get("hra")
    if home_runs is None:
        home_runs = line.get("hr")
    if home_runs is None and line.get("hr_9") is not None:
        home_runs = float(line["hr_9"]) * innings / 9.0
    hits = line.get("ha")
    if hits is None:
        hits = line.get("h")
    return {
        "ip": innings,
        "k": float(strikeouts or 0),
        "bb": float(walks or 0),
        "hr": float(home_runs or 0),
        "h": float(hits or 0),
    }


def regress_pitcher(counts):
    """Pull home runs and hits toward the league. Strikeouts and walks stay on his own innings."""
    innings = counts.get("ip") or 0
    if innings <= 0:
        return dict(counts)
    weight = PITCHER_REGRESSION_IP
    home_runs = (counts["hr"] + (LEAGUE_HR9 / 9.0) * weight) / (innings + weight) * innings
    hits = (counts["h"] + (LEAGUE_H9 / 9.0) * weight) / (innings + weight) * innings
    return {
        "ip": innings,
        "k": counts["k"],
        "bb": counts["bb"],
        "hr": home_runs,
        "h": hits,
    }


def pitcher_rates(counts):
    innings = counts.get("ip") or 0
    if innings <= 0:
        return None
    fip = ((13.0 * counts["hr"]) + (3.0 * counts["bb"]) - (2.0 * counts["k"])) / innings + FIP_CONSTANT
    return {
        "ip": round(innings, 1),
        "k_9": round(9.0 * counts["k"] / innings, 2),
        "bb_9": round(9.0 * counts["bb"] / innings, 2),
        "hr_9": round(9.0 * counts["hr"] / innings, 2),
        "fip": round(fip, 2),
    }


def pitcher_true_talent(line):
    return pitcher_rates(regress_pitcher(pitcher_counts(line)))


def blend_pitcher(prior_counts, season_counts, week):
    live_weight = 0.0 if week <= 1 else 1.0
    mixed = _add(
        _scale(prior_counts, prior_weight(week), PITCHER_KEYS),
        _scale(season_counts, live_weight, PITCHER_KEYS),
        PITCHER_KEYS,
    )
    return pitcher_rates(mixed)


def _round_counts(counts, keys):
    return {key: round(float(counts.get(key, 0) or 0), 3) for key in keys}


def build_side(prior_line, live_line, previous_counts, week, *, kind):
    """
    One side of a card. ``previous_counts`` is last week's observed season
    line. Without it, a later week can still publish talent, but it cannot
    say what was new this week.
    """
    if kind == "hit":
        observe = hitter_counts
        regress = regress_hitter
        blend = blend_hitter
        keys = HITTER_KEYS
        rates = hitter_rates
    else:
        observe = pitcher_counts
        regress = regress_pitcher
        blend = blend_pitcher
        keys = PITCHER_KEYS
        rates = pitcher_rates

    observed_prior = observe(prior_line)
    sample_key = "pa" if kind == "hit" else "ip"
    has_prior = (observed_prior.get(sample_key) or 0) > 0
    season = observe(live_line)
    has_season = (season.get(sample_key) or 0) > 0
    if not has_prior and not has_season:
        return None
    prior = regress(observed_prior) if has_prior else (empty_hitter() if kind == "hit" else empty_pitcher())
    usage_known = week <= 1 or previous_counts is not None
    if week <= 1 or previous_counts is None:
        week_counts = empty_hitter() if kind == "hit" else empty_pitcher()
    else:
        week_counts = _delta(season, previous_counts, keys)
    if has_prior:
        talent = blend(prior, season, week)
    elif week <= 1:
        talent = None
    else:
        talent = rates(season)
    return {
        "talent": talent,
        "prior": rates(prior) if prior_line else None,
        "week": _round_counts(week_counts, keys),
        "season": _round_counts(season, keys),
        "usage_known": usage_known,
    }


def build_card(prior_hit, live_hit, previous_hit, prior_pitch, live_pitch, previous_pitch, week):
    """The stored card for one player and one week."""
    hitting = build_side(prior_hit, live_hit, previous_hit, week, kind="hit")
    pitching = build_side(prior_pitch, live_pitch, previous_pitch, week, kind="pitch")
    return {
        "week": week,
        "prior_weight": prior_weight(week),
        "prior_percent": prior_percent(week),
        "summary": blend_sentence(week),
        "hitting": hitting,
        "pitching": pitching,
    }


def majors_line(player, year, side):
    """The majors line already stored on the player, or None."""
    lines = player.hit_stats() if side == "hit" else player.pit_stats()
    chosen = None
    for line in lines:
        if int(line.get("year") or 0) != int(year):
            continue
        if line.get("type") not in (None, "", "majors"):
            continue
        chosen = line
    return chosen
