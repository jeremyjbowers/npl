from npl import utils
from config.dev import settings

all_players = []
for t in settings.TEAMS:
    team_players = utils.get_sheet(settings.ROSTER_SHEET_ID, f"{t}!A:V", value_cutoff=None)
    team_players = [utils.format_player_row(row, t) for row in team_players if utils.is_player(row)]

    for p in team_players:
        print(p)