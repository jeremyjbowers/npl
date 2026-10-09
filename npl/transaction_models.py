"""Workflow records for trades, waivers, signings, auctions, and drafts.

Imported at the bottom of npl.models so Django registers these on the npl app.
"""

from django.conf import settings
from django.db import models

from npl.models import (
    Auction,
    BaseModel,
    DraftPick,
    Player,
    Season,
    Team,
    Transaction,
)


class TransactionProposal(BaseModel):
    """A manager-submitted transaction waiting on agreement or Monday processing."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    AWAITING = "awaiting_agreement"
    AGREED = "agreed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXECUTED = "executed"
    VOIDED = "voided"
    STATUS_CHOICES = (
        (DRAFT, "Draft"),
        (PROPOSED, "Proposed"),
        (AWAITING, "Awaiting agreement"),
        (AGREED, "Agreed"),
        (REJECTED, "Rejected"),
        (WITHDRAWN, "Withdrawn"),
        (EXECUTED, "Executed"),
        (VOIDED, "Voided"),
    )

    WEB = "web"
    API = "api"
    MCP = "mcp"
    SHEET = "sheet"
    SOURCE_CHOICES = (
        (WEB, "Web form"),
        (API, "API"),
        (MCP, "MCP"),
        (SHEET, "Sheet import"),
    )

    season = models.ForeignKey(Season, on_delete=models.SET_NULL, blank=True, null=True)
    kind = models.CharField(max_length=64)
    transaction_type = models.ForeignKey(
        "npl.TransactionType", on_delete=models.SET_NULL, blank=True, null=True
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PROPOSED)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="transaction_proposals",
    )
    originating_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="proposed_transactions"
    )
    effective_date = models.DateField(blank=True, null=True)
    processing_week = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=WEB)
    executed_at = models.DateTimeField(blank=True, null=True)
    contract_terms = models.JSONField(blank=True, null=True)
    auction = models.ForeignKey(
        Auction, on_delete=models.SET_NULL, blank=True, null=True, related_name="proposals"
    )

    class Meta:
        ordering = ["-created"]

    def __unicode__(self):
        return f"{self.originating_team} {self.kind} ({self.status})"

    @property
    def kind_label(self):
        from npl.transactions.catalog import KINDS

        kind = KINDS.get(self.kind)
        return kind["label"] if kind else self.kind


class TransactionParty(BaseModel):
    ORIGINATOR = "originator"
    COUNTERPARTY = "counterparty"
    ROLE_CHOICES = (
        (ORIGINATOR, "Originator"),
        (COUNTERPARTY, "Counterparty"),
    )
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    AGREEMENT_CHOICES = (
        (NOT_REQUIRED, "Not required"),
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
    )

    proposal = models.ForeignKey(
        TransactionProposal, on_delete=models.CASCADE, related_name="parties"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="transaction_parties")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    agreement_status = models.CharField(
        max_length=20, choices=AGREEMENT_CHOICES, default=NOT_REQUIRED
    )
    agreed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="transaction_agreements",
    )
    agreed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["proposal", "role", "team"]

    def __unicode__(self):
        return f"{self.team} {self.role} {self.agreement_status}"


class TransactionAsset(BaseModel):
    proposal = models.ForeignKey(
        TransactionProposal, on_delete=models.CASCADE, related_name="assets"
    )
    from_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assets_sent",
    )
    to_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assets_received",
    )
    asset_type = models.CharField(max_length=32)
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    draft_pick = models.ForeignKey(DraftPick, on_delete=models.SET_NULL, blank=True, null=True)
    mlb_id = models.CharField(max_length=255, blank=True, null=True)
    scoresheet_id = models.CharField(max_length=255, blank=True, null=True)
    raw_label = models.CharField(max_length=255, blank=True, null=True)
    qualifier = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Distinguishes a Rule 5 draft pick from a Rule 4 pick.",
    )
    amount = models.IntegerField(blank=True, null=True)
    contract_terms = models.JSONField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    executed_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="source_assets",
    )

    class Meta:
        ordering = ["proposal", "id"]

    def __unicode__(self):
        label = self.raw_label or self.asset_type
        return f"{self.asset_type}: {label}"


class Waiver(BaseModel):
    OUTRIGHT = "outright"
    RELEASE = "release"
    TRADE = "trade"
    RULE5 = "rule5"
    TYPE_CHOICES = (
        (OUTRIGHT, "Outright"),
        (RELEASE, "Release"),
        (TRADE, "Trade"),
        (RULE5, "Rule 5"),
    )
    OPEN = "open"
    CLEARED = "cleared"
    CLAIMED = "claimed"
    RETURNED = "returned"
    WITHDRAWN = "withdrawn"
    STATUS_CHOICES = (
        (OPEN, "Open"),
        (CLEARED, "Cleared"),
        (CLAIMED, "Claimed"),
        (RETURNED, "Returned"),
        (WITHDRAWN, "Withdrawn"),
    )
    KEEP = "keep_40"
    RELEASE = "release"
    DISPOSITION_CHOICES = (
        ("", ""),
        (KEEP, "Keep on 40-man if cleared"),
        (RELEASE, "Release if cleared"),
    )

    proposal = models.OneToOneField(
        TransactionProposal, on_delete=models.CASCADE, related_name="waiver"
    )
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    placing_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="waivers_placed")
    waiver_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=OUTRIGHT)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=OPEN)
    salary = models.IntegerField(blank=True, null=True)
    mls_snapshot = models.CharField(max_length=32, blank=True, null=True)
    options_remaining = models.IntegerField(blank=True, null=True)
    veteran_disposition = models.CharField(
        max_length=16, choices=DISPOSITION_CHOICES, blank=True, default=""
    )
    service_class = models.CharField(max_length=32, blank=True, default="")
    placed_on = models.DateField(blank=True, null=True)
    clears_on = models.DateField(blank=True, null=True)
    opens = models.DateTimeField(blank=True, null=True)
    closes = models.DateTimeField(blank=True, null=True)
    claiming_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="waivers_claimed",
    )

    class Meta:
        ordering = ["-placed_on", "-created"]

    def __unicode__(self):
        name = self.player.name if self.player else "player"
        return f"{self.waiver_type} waiver: {name} ({self.placing_team})"


class WaiverClaim(BaseModel):
    waiver = models.ForeignKey(Waiver, on_delete=models.CASCADE, related_name="claims")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="waiver_claims")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["created"]
        unique_together = [("waiver", "team")]

    def __unicode__(self):
        return f"{self.team} claims {self.waiver}"


class DraftSession(BaseModel):
    RULE4 = "rule4"
    RULE5 = "rule5"
    OPEN = "open"
    AA = "aa"
    BALANCE = "balance"
    TYPE_CHOICES = (
        (RULE4, "Rule 4"),
        (RULE5, "Rule 5"),
        (OPEN, "Open"),
        (AA, "AA"),
        (BALANCE, "Balance"),
    )
    SCHEDULED = "scheduled"
    OPEN_STATUS = "open"
    COMPLETE = "complete"
    STATUS_CHOICES = (
        (SCHEDULED, "Scheduled"),
        (OPEN_STATUS, "Open"),
        (COMPLETE, "Complete"),
    )
    OFFSEASON = "offseason"
    MIDSEASON = "midseason"
    HALF_CHOICES = (
        (OFFSEASON, "Offseason"),
        (MIDSEASON, "Midseason"),
    )

    year = models.CharField(max_length=4)
    half = models.CharField(max_length=16, choices=HALF_CHOICES, default=OFFSEASON)
    draft_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=SCHEDULED)
    current_pick = models.ForeignKey(
        DraftPick, on_delete=models.SET_NULL, blank=True, null=True, related_name="on_the_clock"
    )
    selection_fee = models.IntegerField(
        default=0, help_text="Cash charged to the selecting club. Rule 5 is $100,000."
    )

    class Meta:
        ordering = ["-year", "draft_type"]

    def __unicode__(self):
        return f"{self.year} {self.draft_type} ({self.status})"


class InjuredListStint(BaseModel):
    SEVEN = "7"
    FIFTY_SIX = "56"
    EOS = "eos"
    COVID = "covid"
    LENGTH_CHOICES = (
        (SEVEN, "7-day"),
        (FIFTY_SIX, "56-day"),
        (EOS, "End of season"),
        (COVID, "COVID"),
    )

    proposal = models.ForeignKey(
        TransactionProposal,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="il_stints",
    )
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="il_stints")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="il_stints")
    length = models.CharField(max_length=8, choices=LENGTH_CHOICES)
    placed_on = models.DateField(blank=True, null=True)
    earliest_reinstatement = models.DateField(blank=True, null=True)
    mlb_activation = models.DateField(blank=True, null=True)
    required_activation = models.DateField(blank=True, null=True)
    penalty_amount = models.IntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    active_stint = models.BooleanField(default=True)

    class Meta:
        ordering = ["-placed_on", "-created"]

    def __unicode__(self):
        return f"{self.player} {self.length} IL ({self.team})"


class RestrictedListStint(BaseModel):
    proposal = models.ForeignKey(
        TransactionProposal,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="restricted_stints",
    )
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="restricted_stints")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="restricted_stints")
    rl_type = models.CharField(max_length=32, blank=True, null=True)
    counts_against_40 = models.BooleanField(default=False)
    accrues_service = models.BooleanField(default=False)
    accrues_salary = models.BooleanField(default=False)
    placed_on = models.DateField(blank=True, null=True)
    mlb_reinstatement = models.DateField(blank=True, null=True)
    placed_back_by = models.DateField(blank=True, null=True)
    salary = models.IntegerField(blank=True, null=True)
    suspension_days = models.IntegerField(blank=True, null=True)
    unpaid_portion = models.IntegerField(blank=True, null=True)
    service_time_debit = models.IntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    active_stint = models.BooleanField(default=True)

    class Meta:
        ordering = ["-placed_on", "-created"]

    def __unicode__(self):
        return f"{self.player} RL {self.rl_type or ''} ({self.team})"


class MinorLeagueOptOut(BaseModel):
    """Dates and salaries from the Minor League Opt-Outs block of the waiver tab."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="opt_outs")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="opt_outs")
    season = models.ForeignKey(Season, on_delete=models.SET_NULL, blank=True, null=True)
    salary = models.IntegerField(blank=True, null=True)
    salary_june_1 = models.IntegerField(blank=True, null=True)
    salary_july_15 = models.IntegerField(blank=True, null=True)
    salary_august_15 = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ["team", "player"]

    def __unicode__(self):
        return f"{self.player} opt-out ({self.team})"


class Rule4Slot(BaseModel):
    year = models.IntegerField()
    round = models.IntegerField()
    pick = models.IntegerField()
    round_pick = models.IntegerField()
    slot_value = models.IntegerField()

    class Meta:
        ordering = ["-year", "round", "pick"]
        unique_together = [("year", "round", "pick")]

    def __unicode__(self):
        return f"{self.year} R{self.round} P{self.pick} ${self.slot_value}"


class InLimboAssignment(BaseModel):
    """Seven days to trade or outright the player. Not a restricted-list stint."""

    proposal = models.OneToOneField(
        TransactionProposal, on_delete=models.CASCADE, related_name="limbo"
    )
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="limbo_assignments")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="limbo_assignments")
    placed_on = models.DateField(blank=True, null=True)
    deadline = models.DateField(blank=True, null=True)
    reason = models.CharField(max_length=64, blank=True, default="")
    notes = models.TextField(blank=True, null=True)
    active_assignment = models.BooleanField(default=True)

    class Meta:
        ordering = ["-placed_on", "-created"]

    def __unicode__(self):
        return f"{self.player} in limbo ({self.team})"


class FreeAgentListing(BaseModel):
    """One row in a free-agent pool. Auction participation is why a player is listed, not a log verb."""

    MLB_CURRENT = "mlb_current"
    MILB_CURRENT = "milb_current"
    MLB_PRIOR = "mlb_prior"
    MILB_PRIOR = "milb_prior"
    POOL_CHOICES = (
        (MLB_CURRENT, "Current MLB free agents"),
        (MILB_CURRENT, "Current free agents with no MLB service"),
        (MLB_PRIOR, "Earlier MLB free agents"),
        (MILB_PRIOR, "Earlier free agents with no MLB service at release"),
    )

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="free_agent_listings")
    pool = models.CharField(max_length=32, choices=POOL_CHOICES)
    season_year = models.IntegerField()
    former_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, blank=True, null=True, related_name="former_free_agents"
    )
    entered_via_auction = models.BooleanField(default=False)
    sta = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        ordering = ["-season_year", "pool", "player"]
        unique_together = [("player", "pool", "season_year")]

    def __unicode__(self):
        return f"{self.player} {self.pool} {self.season_year}"


class Rule5Selection(BaseModel):
    """One slot on a Rule 5 board: selected, passed, skipped, or ineligible."""

    OPEN = "open"
    SELECTED = "selected"
    PASS = "pass"
    SKIP = "skip"
    INELIGIBLE = "ineligible"
    OUTCOME_CHOICES = (
        (OPEN, "Open"),
        (SELECTED, "Selected"),
        (PASS, "Pass"),
        (SKIP, "Skip"),
        (INELIGIBLE, "Ineligible"),
    )

    session = models.ForeignKey(DraftSession, on_delete=models.CASCADE, related_name="rule5_slots")
    round_number = models.IntegerField()
    pick_number = models.IntegerField()
    original_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, blank=True, null=True, related_name="rule5_original_slots"
    )
    holding_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="rule5_held_slots",
        help_text="The club named in TRADED?, when the slot has been dealt.",
    )
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES, default=OPEN)
    player = models.ForeignKey(Player, on_delete=models.SET_NULL, blank=True, null=True)
    selected_from = models.ForeignKey(
        Team, on_delete=models.SET_NULL, blank=True, null=True, related_name="rule5_players_lost"
    )

    class Meta:
        ordering = ["session", "round_number", "pick_number"]
        unique_together = [("session", "round_number", "pick_number")]

    def __unicode__(self):
        return f"R{self.round_number}.{self.pick_number} {self.outcome}"
