"""Weekly schedule, the computer's instructions, and the player cards.

Imported at the bottom of npl.models so Django registers these on the npl app.
Games are not played one plate appearance at a time. A week is simulated on
Sunday, and the thing that gets kept is the box score.
"""

from django.db import models

from npl.computer_manager import (
    BULLPEN_CHOICES,
    BUNT_CHOICES,
    DEFENSE_SITUATIONS,
    HOOK_CHOICES,
    HIT_AND_RUN_CHOICES,
    PH_SITUATIONS,
    RUN_SITUATIONS,
    STEAL_CHOICES,
)
from npl.models import BaseModel, Player, Season, Team


class ScheduleWeek(BaseModel):
    """One Monday-to-Sunday slice of the season."""

    DIVISION = "division"
    LEAGUE = "league"
    INTERLEAGUE = "interleague"
    KIND_CHOICES = (
        (DIVISION, "Division"),
        (LEAGUE, "League"),
        (INTERLEAGUE, "Interleague"),
    )

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="schedule_weeks")
    number = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    lineup_due = models.DateField(help_text="Monday. The card locks at the end of this day, Eastern time.")
    simulated_on = models.DateField(help_text="Sunday, when the week's games are simulated together.")
    seed = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["season", "number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "number"], name="npl_schedule_week_season_number"),
        ]

    def __str__(self):
        return f"{self.season.year} week {self.number}"


class WeekSeries(BaseModel):
    """The opponent a club plays for the six games of a week."""

    week = models.ForeignKey(ScheduleWeek, on_delete=models.CASCADE, related_name="series")
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="home_weeks")
    road_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="road_weeks")
    games = models.PositiveSmallIntegerField(default=6)

    class Meta:
        ordering = ["week", "home_team__abbreviation"]

    def __str__(self):
        return f"{self.road_team.abbreviation} at {self.home_team.abbreviation}, week {self.week.number}"


class WeekGame(BaseModel):
    """
    One game inside the week's series.

    ``box_score`` is the only public record. The shape, filled by the Sunday
    batch, is line, away, home, win, loss, and save. Batting rows carry name,
    ab, r, h, rbi, bb, and k. Pitching rows carry name, ip, h, r, er, bb, and k.
    """

    series = models.ForeignKey(WeekSeries, on_delete=models.CASCADE, related_name="results")
    number = models.PositiveSmallIntegerField()
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    road_score = models.PositiveSmallIntegerField(null=True, blank=True)
    box_score = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["series", "number"]
        constraints = [
            models.UniqueConstraint(fields=["series", "number"], name="npl_week_game_series_number"),
        ]

    def __str__(self):
        return f"{self.series} game {self.number}"

    @property
    def is_played(self):
        return self.home_score is not None and self.road_score is not None


class WeeklyPlan(BaseModel):
    """The instructions the computer uses because nobody sits the game."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="weekly_plans")
    series = models.ForeignKey(WeekSeries, on_delete=models.CASCADE, related_name="plans")
    usage = models.CharField(max_length=16, choices=BULLPEN_CHOICES, default="traditional")
    hook = models.CharField(max_length=16, choices=HOOK_CHOICES, default="normal")
    steal = models.CharField(max_length=16, choices=STEAL_CHOICES, default="normal")
    bunt = models.CharField(max_length=16, choices=BUNT_CHOICES, default="never")
    hit_and_run = models.CharField(max_length=16, choices=HIT_AND_RUN_CHOICES, default="never")
    lineup_saved = models.BooleanField(default=False)
    rotation_saved = models.BooleanField(default=False)
    bullpen_saved = models.BooleanField(default=False)
    bench_saved = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "series"], name="npl_weekly_plan_team_series"),
        ]

    def __str__(self):
        return f"{self.team.abbreviation} week {self.series.week.number}"


class LineupSlot(BaseModel):
    HAND_CHOICES = (("R", "Against right-handers"), ("L", "Against left-handers"))

    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="lineup_slots")
    hand = models.CharField(max_length=1, choices=HAND_CHOICES)
    order = models.PositiveSmallIntegerField()
    position = models.CharField(max_length=8)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="lineup_slots")

    class Meta:
        ordering = ["hand", "order"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "hand", "order"], name="npl_lineup_slot_order"),
            models.UniqueConstraint(fields=["plan", "hand", "position"], name="npl_lineup_slot_position"),
            models.UniqueConstraint(fields=["plan", "hand", "player"], name="npl_lineup_slot_player"),
        ]


class RotationSlot(BaseModel):
    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="rotation_slots")
    game_number = models.PositiveSmallIntegerField()
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="rotation_slots")

    class Meta:
        ordering = ["game_number"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "game_number"], name="npl_rotation_slot_game"),
        ]


class BullpenSlot(BaseModel):
    ROLE_CHOICES = (
        ("closer", "Closer"),
        ("sirp", "Setup"),
        ("mirp", "Long relief"),
        ("mopup", "Mop-up"),
        ("lefty", "Lefty specialist"),
        ("righty", "Righty specialist"),
    )

    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="bullpen_slots")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    order = models.PositiveSmallIntegerField()
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="bullpen_slots")

    class Meta:
        ordering = ["role", "order"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "player"], name="npl_bullpen_slot_player"),
            models.UniqueConstraint(fields=["plan", "role", "order"], name="npl_bullpen_slot_order"),
        ]


class PinchHitRule(BaseModel):
    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="pinch_hits")
    vs_hand = models.CharField(max_length=1)
    order = models.PositiveSmallIntegerField()
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="pinch_hit_rules")
    for_player = models.ForeignKey(
        Player, on_delete=models.CASCADE, null=True, blank=True, related_name="pinch_hit_targets"
    )
    earliest_inning = models.PositiveSmallIntegerField(default=7)
    situation = models.CharField(max_length=24, choices=PH_SITUATIONS, default="tied_or_trailing")

    class Meta:
        ordering = ["vs_hand", "order"]


class DefenseSub(BaseModel):
    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="defense_subs")
    order = models.PositiveSmallIntegerField()
    out_player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="defense_replaced")
    in_player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="defense_replacements")
    earliest_inning = models.PositiveSmallIntegerField(default=8)
    situation = models.CharField(max_length=24, choices=DEFENSE_SITUATIONS, default="leading")

    class Meta:
        ordering = ["order"]


class PinchRunRule(BaseModel):
    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="pinch_runs")
    order = models.PositiveSmallIntegerField()
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="pinch_run_rules")
    for_player = models.ForeignKey(
        Player, on_delete=models.CASCADE, null=True, blank=True, related_name="pinch_run_targets"
    )
    earliest_inning = models.PositiveSmallIntegerField(default=7)
    situation = models.CharField(max_length=16, choices=RUN_SITUATIONS, default="close")

    class Meta:
        ordering = ["order"]


class PlayerWeekCard(BaseModel):
    """
    One player's true talent after this week's usage has been folded in.

    ``true_talent`` is the updated measure. ``week_usage`` is the playing
    time that was new since the previous card. ``season_usage`` is the
    observed season line the next card diffs against.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="week_cards")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="week_cards")
    week = models.PositiveSmallIntegerField()
    prior_weight = models.FloatField(default=1)
    true_talent = models.JSONField(default=dict, blank=True)
    week_usage = models.JSONField(default=dict, blank=True)
    season_usage = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["season", "week", "player__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["player", "season", "week"], name="npl_player_week_card"),
        ]

    def __str__(self):
        return f"{self.player} {self.season.year} week {self.week}"


NPL_SIM = "npl"


class SimTeamSeason(BaseModel):
    """
    One club's simulated season, summed from the week's box scores.

    This is the standings line. ``TeamSeason`` stays the franchise sheet
    (payroll, cap, cash). A purge deletes these rows and the player lines
    whose classification is ``npl``, and leaves the sheet and the MLB lines.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="sim_seasons")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="sim_team_seasons")
    wins = models.PositiveSmallIntegerField(default=0)
    losses = models.PositiveSmallIntegerField(default=0)
    runs_scored = models.PositiveIntegerField(default=0)
    runs_allowed = models.PositiveIntegerField(default=0)
    division_place = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["season", "team__abbreviation"]
        constraints = [
            models.UniqueConstraint(fields=["team", "season"], name="npl_sim_team_season"),
        ]

    def __str__(self):
        return f"{self.team.abbreviation} {self.season.year}: {self.wins}-{self.losses}"
