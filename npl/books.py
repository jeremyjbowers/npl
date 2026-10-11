"""Write a parsed team tab onto the club, its contracts, and its ledger."""

from decimal import Decimal, InvalidOperation

from django.conf import settings

from npl import models
from npl.sheetload import current_summary, league_minimum


def _blank(text):
    text = (text or "").strip()
    if text in {"", "-"}:
        return ""
    return text


def _player_for(row):
    mlb_id = _blank(row.get("mlb_id"))
    if mlb_id.isdigit():
        found = models.Player.objects.filter(mlb_id=mlb_id).first()
        if found:
            return found
    scoresheet_id = _blank(row.get("scoresheet_id"))
    if scoresheet_id and scoresheet_id != "-":
        return models.Player.objects.filter(scoresheet_id=scoresheet_id).first()
    return None


def _service_decimal(mls):
    text = _blank(mls)
    if "." not in text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def apply_player_row(player, row):
    """Service, options, and the sheet flags that change what a club can do."""
    mls = _blank(row.get("mls"))
    if "." in mls:
        player.mls_time = mls
        service = _service_decimal(mls)
        if service is not None:
            player.service_time = service
    elif mls.isdigit():
        player.mls_year = mls
    options = _blank(row.get("options"))
    if options.isdigit():
        player.options = int(options)
    sta = _blank(row.get("sta"))
    if sta:
        player.sta = sta
        player.status = sta.lower()
        if "QO" in [part.strip() for part in sta.split(",")]:
            player.has_been_qo = True
    if "name_italic" in row:
        player.offseason_fa = bool(row.get("name_italic"))
    for field in (
        "mlb_days",
        "option_days",
        "nonroster_days",
        "sos_service_years",
        "sos_service_days",
    ):
        if row.get(field) is not None:
            setattr(player, field, row[field])
    if "option_used" in row and row.get("option_used") is not None:
        player.option_used = bool(row["option_used"])
    player.save()


def apply_contracts(team, parsed):
    for row in parsed.get("players") or []:
        player = _player_for(row)
        if player is None:
            continue
        apply_player_row(player, row)
        contract = models.Contract(team=team, player=player)
        years = row.get("years") or []
        contract.total_years = len(years)
        contract.total_amount = sum(item["amount"] for item in years)
        contract.notes = row.get("terms") or ""
        contract.terms_pending = bool(row.get("terms_pending"))
        if row.get("buyout") is not None:
            contract.can_buyout = True
            contract.buyout_amount = row["buyout"]
            contract.buyout = str(row["buyout"])
        contract.save()
        for item in years:
            models.ContractYear.objects.create(
                contract=contract,
                year=item["year"],
                amount=item["amount"],
                salary_class=item.get("salary_class") or "guaranteed",
            )


def _set_if(obj, field, value):
    if value is not None:
        setattr(obj, field, value)


def apply_finances(team, parsed, year=None):
    """Summary row, yearly projections, and the FINANCIALS ledger."""
    year = year or settings.LEAGUE_YEAR
    summary = current_summary(parsed, year)
    contract_salary = 0
    for row in parsed.get("players") or []:
        for item in row.get("years") or []:
            if item["year"] == year:
                contract_salary += item["amount"]
    carried = 0
    for line in parsed.get("lines") or []:
        if line["year"] == year and "carried" in f"{line['label']} {line['detail']}".lower():
            carried += line["amount"]

    if summary:
        _set_if(team, "mlb_payroll", summary.get("payroll"))
        _set_if(team, "cap_space", summary.get("cap_space"))
        _set_if(team, "cash", summary.get("cash"))
        _set_if(team, "luxury_cap_space", summary.get("luxury"))
        if summary.get("cash") is not None:
            team.cash_borrowing = max(0, -summary["cash"])
    team.contract_salary = contract_salary
    team.carried_salary = carried
    if parsed.get("founded"):
        team.initial_season = parsed["founded"]
    team.save()

    models.ClubLedgerEntry.objects.filter(team=team).delete()
    models.ClubLedgerEntry.objects.bulk_create(
        [
            models.ClubLedgerEntry(
                team=team,
                year=line["year"],
                book=line["book"],
                label=line["label"][:255],
                detail=(line.get("detail") or "")[:255],
                amount=line["amount"],
                row_order=line.get("row_order") or 0,
            )
            for line in parsed.get("lines") or []
        ]
    )

    for season_year, figures in (parsed.get("projections") or {}).items():
        season = models.Season.objects.filter(year=season_year).first()
        if season is None:
            season = models.Season(year=season_year)
        if figures.get("salary_cap") is not None:
            season.salary_cap = figures["salary_cap"]
        minimum = league_minimum(season_year)
        if minimum is not None and season.league_min is None:
            season.league_min = minimum
        season.save()
        team_season = models.TeamSeason.objects.filter(team=team, season=season).first()
        if team_season is None:
            team_season = models.TeamSeason(team=team, season=season)
        _set_if(team_season, "mlb_payroll", figures.get("payroll"))
        _set_if(team_season, "cap_space", figures.get("cap_space"))
        _set_if(team_season, "cash", figures.get("cash"))
        if season_year == year:
            team_season.contract_salary = contract_salary
            team_season.carried_salary = carried
            if summary:
                _set_if(team_season, "luxury_cap_space", summary.get("luxury"))
                _set_if(team_season, "roster_85_man", summary.get("roster_85"))
                _set_if(team_season, "roster_40_man", summary.get("roster_40"))
                _set_if(team_season, "roster_30_man", summary.get("roster_30"))
                if summary.get("cash") is not None:
                    team_season.cash_borrowing = max(0, -summary["cash"])
                if summary.get("payroll") is not None:
                    team_season.mlb_payroll = summary["payroll"]
                if summary.get("cap_space") is not None:
                    team_season.cap_space = summary["cap_space"]
                if summary.get("cash") is not None:
                    team_season.cash = summary["cash"]
        team_season.save()


def apply_service_rows(records):
    for record in records:
        player = _player_for(record)
        if player is None:
            continue
        apply_player_row(player, record)


def apply_key_sheet(parsed):
    """Season constants and the cap, cash, and IFA columns on the Key tab."""
    season_info = parsed.get("season") or {}
    year = season_info.get("year") or settings.LEAGUE_YEAR
    season = models.Season.objects.filter(year=year).first()
    if season is None:
        season = models.Season(year=year)
    _set_if(season, "salary_cap", season_info.get("salary_cap"))
    _set_if(season, "league_min", season_info.get("league_min") or league_minimum(year))
    _set_if(season, "ifa_deadline", season_info.get("ifa_deadline"))
    _set_if(season, "end_of_season", season_info.get("end_of_season"))
    season.save()

    for row in parsed.get("teams") or []:
        team = models.Team.objects.filter(full_name=row["full_name"]).first()
        if team is None:
            short_name = row["full_name"].split()[-1].strip()
            team = models.Team.objects.filter(short_name=short_name).first()
        if team is None:
            continue
        _set_if(team, "cap_space", row.get("cap_space"))
        _set_if(team, "cash", row.get("cash"))
        _set_if(team, "ifa", row.get("ifa"))
        team.save()
        team_season = models.TeamSeason.objects.filter(team=team, season=season).first()
        if team_season is None:
            team_season = models.TeamSeason(team=team, season=season)
        _set_if(team_season, "cap_space", row.get("cap_space"))
        _set_if(team_season, "cash", row.get("cash"))
        _set_if(team_season, "ifa", row.get("ifa"))
        _set_if(team_season, "roster_85_man", row.get("roster_85"))
        _set_if(team_season, "roster_40_man", row.get("roster_40"))
        _set_if(team_season, "roster_30_man", row.get("roster_30"))
        team_season.save()
    return season
