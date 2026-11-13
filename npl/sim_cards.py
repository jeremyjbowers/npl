"""The engine cards for one game, read off the weekly true-talent cards."""

from npl.cards import LEAGUE_BABIP, LEAGUE_BB9, LEAGUE_H9, LEAGUE_HR9, LEAGUE_K9

HBP_PER_PA = 0.011
HBP_PER_9 = 0.3
SINGLE_SHARE = 0.75
DOUBLE_SHARE = 0.22


class SimError(Exception):
    def __init__(self, reasons):
        if isinstance(reasons, str):
            reasons = [reasons]
        self.reasons = list(reasons)
        super().__init__(" ".join(self.reasons))


def engine_hitter_rates(talent):
    """Eight outcome rates per plate appearance. They sum to 1."""
    k = float(talent.get("k_pct") or 0) / 100.0
    bb = float(talent.get("bb_pct") or 0) / 100.0
    hr = float(talent.get("hr_pa") or 0)
    hbp = HBP_PER_PA
    babip = LEAGUE_BABIP if talent.get("babip") is None else float(talent["babip"])
    fixed = _cap(k, bb, hbp, hr)
    k, bb, hbp, hr = fixed
    bip = max(0.0, 1.0 - (k + bb + hbp + hr))
    hits = min(bip, max(0.0, babip) * bip)
    single = hits * SINGLE_SHARE
    double = hits * DOUBLE_SHARE
    triple = max(0.0, hits - single - double)
    bip_out = max(0.0, bip - (single + double + triple))
    rates = {
        "k": k,
        "bb": bb,
        "hbp": hbp,
        "single": single,
        "double": double,
        "triple": triple,
        "hr": hr,
        "bip_out": bip_out,
    }
    rates["bip_out"] += 1.0 - sum(rates.values())
    return rates


def engine_pitcher_rates(talent):
    """Outcome rates per batter faced. ``h`` is hits that are not home runs."""
    k9 = _or(talent.get("k_9"), LEAGUE_K9)
    bb9 = _or(talent.get("bb_9"), LEAGUE_BB9)
    hr9 = _or(talent.get("hr_9"), LEAGUE_HR9)
    h9 = _or(talent.get("h_9"), LEAGUE_H9)
    non_hr = max(0.0, h9 - hr9)
    faced = 27.0 + h9 + bb9 + HBP_PER_9
    rates = {
        "k": k9 / faced,
        "bb": bb9 / faced,
        "hbp": HBP_PER_9 / faced,
        "hr": hr9 / faced,
        "h": non_hr / faced,
    }
    total = sum(rates.values())
    if total >= 1:
        rates = {key: value * 0.95 / total for key, value in rates.items()}
    return {key: min(value, 0.99) for key, value in rates.items()}


def hitter_card(player, talent, position):
    return {
        "id": player.mlb_id,
        "name": player.name,
        "position": position,
        "defense": {"rating": 0.0, "measured_at": position},
        "wrc_plus": 100.0,
        "rates": engine_hitter_rates(talent),
    }


def pitcher_card(player, talent, year, starter):
    age = 28
    if player.birthdate:
        age = max(1, year - player.birthdate.year)
    pitches = 95.0 if starter else 18.0
    return {
        "id": player.mlb_id,
        "name": player.name,
        "defense": {"rating": 0.0, "measured_at": "P"},
        "rates": engine_pitcher_rates(talent),
        "fatigue": {
            "role": "starter" if starter else "reliever",
            "age": age,
            "season_pitches_per_appearance": pitches,
            "career_pitches_per_appearance": pitches,
            "season_appearances": 10,
        },
    }


def _or(value, fallback):
    return fallback if value is None else float(value)


def _cap(k, bb, hbp, hr):
    parts = [max(0.0, k), max(0.0, bb), max(0.0, hbp), max(0.0, hr)]
    total = sum(parts)
    if total >= 1:
        parts = [part * 0.95 / total for part in parts]
    return parts
