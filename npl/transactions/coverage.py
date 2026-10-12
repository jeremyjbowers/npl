"""Who pays a traded contract, and a coverage piece for a player who is staying.

In the regular season and the postseason, the club that sends a player covers
the current league year and the club that receives him covers every later year.
In the offseason, the club that receives him covers every year. A year can be
split, and the dollars cannot go past that year's salary.
"""

from django.conf import settings

from npl import models
from npl.transactions.catalog import ASSET_COVERAGE, ASSET_PLAYER


def league_year():
    return int(settings.LEAGUE_YEAR)


def default_payer(year, from_team_id, to_team_id, phase):
    """The club that covers this year unless the clubs change it."""
    if phase == models.Season.OFFSEASON:
        return to_team_id
    if int(year) == league_year():
        return from_team_id
    return to_team_id


def default_coverage(years, from_team_id, to_team_id, phase):
    rows = []
    for year in years:
        salary = int(year["amount"] or 0)
        rows.append(
            {
                "year": int(year["year"]),
                "salary": salary,
                "payers": [
                    {
                        "team": default_payer(year["year"], from_team_id, to_team_id, phase),
                        "percent": 100,
                        "amount": salary,
                    }
                ],
            }
        )
    return rows


def years_by_player(players):
    """player id -> contract years from the league year forward, current club first."""
    players = list(players)
    if not players:
        return {}
    team_of = {player.pk: player.team_id for player in players}
    rows = models.ContractYear.objects.filter(
        contract__player_id__in=team_of,
        year__gte=league_year(),
    ).values("contract__player_id", "contract__team_id", "year", "amount")
    chosen = {}
    for row in rows:
        player_id = row["contract__player_id"]
        year = int(row["year"])
        on_club = row["contract__team_id"] == team_of.get(player_id)
        current = chosen.get((player_id, year))
        if current is None or (on_club and not current["on_club"]):
            chosen[(player_id, year)] = {
                "year": year,
                "amount": int(row["amount"] or 0),
                "on_club": on_club,
            }
    grouped = {}
    for (player_id, _year), item in chosen.items():
        grouped.setdefault(player_id, []).append({"year": item["year"], "amount": item["amount"]})
    for items in grouped.values():
        items.sort(key=lambda item: item["year"])
    return grouped


def _team_id(value):
    if value is None or value == "":
        return None
    if hasattr(value, "pk"):
        return value.pk
    return int(value)


def iter_payer_ids(asset):
    terms = asset.get("contract_terms") or {}
    if not isinstance(terms, dict):
        return
    for row in terms.get("coverage") or []:
        for payer in row.get("payers") or []:
            team_id = _team_id(payer.get("team"))
            if team_id is not None:
                yield team_id


def problems_for_trade(assets, club_ids):
    """Problems with salary coverage. club_ids is every club in the deal."""
    club_ids = {int(club_id) for club_id in club_ids}
    moving = [
        asset for asset in assets
        if asset.get("asset_type") == ASSET_PLAYER and asset.get("player") is not None
    ]
    moving_ids = {asset["player"].pk for asset in moving}
    years = years_by_player(asset["player"] for asset in moving)
    coverage_players = []
    for asset in assets:
        if asset.get("asset_type") == ASSET_COVERAGE and asset.get("player") is not None:
            coverage_players.append(asset["player"])
    coverage_years = years_by_player(coverage_players)
    problems = []
    seen_players = set()
    for asset in moving:
        player = asset["player"]
        if player.pk in seen_players:
            problems.append(f"{player.name} is in this trade twice.")
            continue
        seen_players.add(player.pk)
        problems.extend(
            _moving_player_problems(player, asset.get("contract_terms") or {}, years.get(player.pk, []), club_ids)
        )
    for asset in assets:
        if asset.get("asset_type") != ASSET_COVERAGE:
            continue
        problems.extend(_coverage_piece_problems(asset, moving_ids, coverage_years, club_ids))
    return problems


def _moving_player_problems(player, terms, years, club_ids):
    if not years:
        return []
    rows = {int(row.get("year")): row for row in (terms.get("coverage") or []) if row.get("year") not in (None, "")}
    problems = []
    missing = []
    for year in years:
        row = rows.get(int(year["year"]))
        if row is None or not (row.get("payers") or []):
            missing.append(str(year["year"]))
            continue
        problems.extend(
            _year_problems(player.name, int(year["year"]), int(year["amount"] or 0), row.get("payers") or [], club_ids)
        )
    if missing:
        listed = ", ".join(missing)
        problems.append(
            f"{player.name} needs coverage for {listed}. "
            "In season the sending club covers this year and the receiving club covers later years. "
            "In the offseason the receiving club covers every year."
        )
    return problems


def _year_problems(player_name, year, salary, payers, club_ids):
    problems = []
    total = 0
    for payer in payers:
        team_id = _team_id(payer.get("team"))
        if team_id not in club_ids:
            problems.append(f"{player_name}'s {year} coverage names a club that is not in the trade.")
            continue
        amount = payer.get("amount")
        percent = payer.get("percent")
        if salary:
            if amount in (None, "") and percent not in (None, ""):
                amount = int(round(salary * int(percent) / 100))
            amount = int(amount or 0)
            if amount < 0 or amount > salary:
                problems.append(
                    f"{player_name}'s {year} coverage is ${amount:,}, and the salary is ${salary:,}."
                )
            total += max(amount, 0)
        else:
            percent = int(percent or 0)
            if percent < 1 or percent > 100:
                problems.append(f"{player_name}'s {year} coverage cannot be more than 100%.")
    if salary and not any("coverage is $" in problem for problem in problems):
        if total != salary:
            problems.append(
                f"{player_name}'s {year} salary is ${salary:,} and the clubs cover ${total:,}. "
                "Cover the year in full, and not more than that."
            )
    elif not salary:
        percent_total = 0
        for payer in payers:
            try:
                percent_total += int(payer.get("percent") or 0)
            except (TypeError, ValueError):
                percent_total += 0
        if percent_total != 100:
            problems.append(f"{player_name}'s {year} coverage has to add up to 100%.")
    return problems


def _coverage_piece_problems(asset, moving_ids, years_by_id, club_ids):
    player = asset.get("player")
    problems = []
    if player is None:
        return ["Salary coverage needs a player."]
    if player.pk in moving_ids:
        return [f"Set {player.name}'s coverage on the years of his contract. He is already in the trade."]
    if player.team_id not in club_ids:
        club = player.team.short_name if player.team_id else "no club"
        return [f"{player.name} is on {club}, so that club has to be in the trade."]
    try:
        year = int(asset.get("contract_terms", {}).get("year"))
    except (TypeError, ValueError, AttributeError):
        return [f"Say which year of {player.name}'s contract is being covered."]
    salary = 0
    for row in years_by_id.get(player.pk, []):
        if int(row["year"]) == year:
            salary = int(row["amount"] or 0)
            break
    amount = asset.get("amount")
    if amount in (None, ""):
        return [f"Say how many dollars of {player.name}'s {year} salary are covered."]
    amount = int(amount)
    if amount < 0:
        return [f"Coverage of {player.name} cannot be negative."]
    if salary and amount > salary:
        return [
            f"Coverage of {player.name} in {year} is ${amount:,}, which is more than the ${salary:,} salary."
        ]
    if not salary:
        percent = (asset.get("contract_terms") or {}).get("percent")
        try:
            percent = int(percent)
        except (TypeError, ValueError):
            percent = None
        if percent is None or percent < 1 or percent > 100:
            return [f"Coverage of {player.name} in {year} cannot be more than 100%."]
    from_team = asset.get("from_team")
    to_team = asset.get("to_team")
    if from_team is None or to_team is None:
        problems.append(f"Say which club covers {player.name}, and which club is relieved.")
    elif _team_id(from_team) == _team_id(to_team):
        problems.append(f"{player.name}'s coverage cannot be paid by the club that is relieved.")
    return problems
