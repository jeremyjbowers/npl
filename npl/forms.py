import json

from django import forms
from django.forms import widgets
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Team, Player, TransactionSubmission, Owner
from users.models import User
from django.db import models
from django.db.models import Q
from npl.transactions.catalog import ASSET_LABELS
from npl.transactions.coverage import problems_for_trade


# What a manager can file from the site. Each headline on the menu links
# straight to that filing. Hints stay here for the detail pages.
TRANSACTION_MENU = (
    {
        "label": "Deals",
        "options": (
            {
                "code": "trade",
                "label": "Trade Proposal",
                "hint": "Pick the clubs, then what each one sends, then who receives it. Cap, cash, IFA dollars, and salary coverage can be included.",
            },
        ),
    },
    {
        "label": "Contracts",
        "options": (
            {
                "code": "signing",
                "label": "Free Agent or Contract Signing",
                "hint": "Offseason major-league deal in points, in-season free agent, minor-league contract, or extension.",
            },
            {
                "code": "ifa_signing",
                "label": "IFA Signing",
                "hint": "An international signing, paid from the club's bonus pool.",
            },
            {
                "code": "offseason",
                "label": "Offseason Transactions",
                "hint": "A spring invitation, or a signing, trade, or extension written out as one note.",
            },
        ),
    },
    {
        "label": "Roster",
        "options": (
            {
                "code": "injured_list",
                "label": "Injured List",
                "hint": "7-day, 56-day, end of season, COVID, or a move between those lists. End-of-season IL needs a link explaining why he will not return.",
            },
            {
                "code": "option_minors",
                "label": "Option to Minor Leagues",
                "hint": "The player is sent to Triple-A and needs an option year left.",
            },
            {
                "code": "purchase_contract",
                "label": "Purchase a Contract",
                "hint": "A player at Double-A or Single-A is brought onto the 40-man by purchasing his contract, not by recalling an option.",
            },
            {
                "code": "recall_option",
                "label": "Recall an Option",
                "hint": "Bring an optioned player back from Triple-A.",
            },
            {
                "code": "release_player",
                "label": "Release Player",
                "hint": "Unconditional release, outright release, or a release that goes through waivers.",
            },
            {
                "code": "limbo_assignment",
                "label": "In Limbo Assignment",
                "hint": "Hold a player for a pending trade, an investigation, or a contract dispute.",
            },
            {
                "code": "restricted_list",
                "label": "Restricted List",
                "hint": "Restricted list, a suspension, paternity, family medical, or bereavement.",
            },
            {
                "code": "foreign_retirement",
                "label": "Foreign/Retirement/Death",
                "hint": "Foreign list, retirement, or death. A foreign-list move needs a link showing he is playing in a foreign league.",
            },
        ),
    },
    {
        "label": "Waivers",
        "options": (
            {
                "code": "waiver_request",
                "label": "Waiver Request",
                "hint": "Ask for outright, trade, or Rule 5 waivers on a player you have.",
            },
            {
                "code": "waiver_claim",
                "label": "Waiver Claim",
                "hint": "Claim a player another club has placed on waivers.",
            },
        ),
    },
)


class TransactionTypeForm(forms.Form):
    """Step 1: Choose transaction type"""
    TRANSACTION_CHOICES = [
        (option["code"], option["label"])
        for group in TRANSACTION_MENU
        for option in group["options"]
    ]
    
    transaction_type = forms.ChoiceField(
        choices=TRANSACTION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'select',
            'style': 'width: 100%;'
        }),
        label="What type of transaction will you be making?"
    )


class BaseTransactionForm(forms.Form):
    """Base form with common fields"""
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Auto-populate team choices for logged-in user
        if self.user and hasattr(self.user, 'owner'):
            # Use the correct reverse relationship - Team.objects.filter(owners=user.owner)
            teams = Team.objects.filter(owners=self.user.owner)
            if teams.exists():
                team_choices = [(team.id, team.full_name) for team in teams]
                self.fields['team'] = forms.ChoiceField(
                    choices=team_choices,
                    widget=forms.Select(attrs={'class': 'select'}),
                    label="Team"
                )
                # Auto-select if only one team
                if len(team_choices) == 1:
                    self.fields['team'].initial = team_choices[0][0]
                    self.fields['team'].widget = forms.HiddenInput()
                    
                # Store the user's team for player filtering
                self.user_team = teams.first() if len(team_choices) == 1 else None
            else:
                self.user_team = None
        else:
            # Fallback for users without owner relationship
            self.fields['team'] = forms.ModelChoiceField(
                queryset=Team.objects.all(),
                widget=forms.Select(attrs={'class': 'select'}),
                label="Team"
            )
            self.user_team = None

    def get_player_queryset(self):
        """Override this method in subclasses to filter players appropriately"""
        return Player.objects.all()
    
    def get_player_level(self, player):
        """Get the level for any player based on their roster status"""
        # Check for special statuses first (IL, Restricted, Retired)
        if player.roster_7dayIL or player.roster_56dayIL or player.roster_eosIL:
            return 'IL'
        elif player.roster_restricted:
            return 'Restricted'
        elif player.roster_retired:
            return 'Retired'
        elif player.roster_foreign:
            return 'Foreign'
        # Then check regular roster levels
        elif player.roster_40man:
            return 'MLB'
        elif player.roster_tripleA or player.roster_tripleA_option:
            return 'AAA'
        elif player.roster_doubleA:
            return 'AA'
        elif player.roster_singleA:
            return 'A'
        elif player.roster_nonroster:
            return 'Rookie'
        else:
            return 'Unknown'
    
    def setup_player_field(self, label="Player", help_text=None):
        """Helper method to setup the player field with appropriate filtering"""
        queryset = self.get_player_queryset()
        
        if queryset.exists():
            # Custom ModelChoiceField with enhanced display
            class PlayerChoiceField(forms.ModelChoiceField):
                def __init__(self, *args, **kwargs):
                    self.form = kwargs.pop('form', None)
                    super().__init__(*args, **kwargs)
                
                def label_from_instance(self, obj):
                    """Enhanced display with position, team, and level info"""
                    label_parts = [obj.name]
                    
                    # Add position if available
                    if obj.simple_position:
                        label_parts.append(f"({obj.simple_position})")
                    elif obj.position:
                        label_parts.append(f"({obj.position})")
                    
                    # Add level information
                    if self.form:
                        level = self.form.get_player_level(obj)
                        level_display = level
                    else:
                        level_display = 'Unknown'
                    
                    # Add team and level info
                    if obj.team:
                        label_parts.append(f"- {obj.team.short_name} ({level_display})")
                    else:
                        label_parts.append(f"- FA ({level_display})")
                    
                    return " ".join(label_parts)
            
            self.fields['player'] = PlayerChoiceField(
                queryset=queryset.select_related('team'),  # Optimize queries
                widget=forms.Select(attrs={
                    'class': 'select',
                    'style': 'width: 100%;'
                }),
                label=label,
                help_text=help_text,
                empty_label="Select a player...",
                form=self  # Pass form instance for level detection
            )
        else:
            # Fallback to text input if no players available
            self.fields['player'] = forms.CharField(
                max_length=255,
                widget=forms.TextInput(attrs={
                    'class': 'input',
                    'placeholder': 'Enter player name'
                }),
                label=label,
                help_text="No eligible players found. Enter player name manually."
            )


class InjuredListForm(BaseTransactionForm):
    """Form for injured list transactions"""
    IL_TYPE_CHOICES = [
        ('7-day', '7-Day IL'),
        ('56-day', '56-Day IL'),
        ('eos', 'End of Season IL'),
        ('covid', 'COVID IL'),
        ('moving', 'Move between IL types'),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name", 
            help_text="Select a player from your team to place on injured list"
        )
    
    def get_player_queryset(self):
        """Only players on the MLB roster or already on IL can be placed on/moved between IL"""
        if self.user_team:
            return Player.objects.filter(
                team=self.user_team, 
                active=True
            ).filter(
                models.Q(roster_40man=True) |  # MLB roster players
                models.Q(roster_7dayIL=True) |  # Already on 7-day IL
                models.Q(roster_56dayIL=True) |  # Already on 56-day IL  
                models.Q(roster_eosIL=True)  # Already on end-of-season IL
            )
        return Player.objects.none()
    
    il_type = forms.ChoiceField(
        choices=IL_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Injured List"
    )
    
    injury_description = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Describe the injury...'
        }),
        label="Injury Description",
        help_text="Provide details about the injury"
    )

    source_url = forms.URLField(
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(attrs={
            "class": "input",
            "placeholder": "https://",
        }),
        label="Source URL",
        help_text="Required for the end-of-season IL. Link to why this player will not return this season.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("il_type") == "eos" and not cleaned.get("source_url"):
            self.add_error(
                "source_url",
                "End-of-season IL needs a URL explaining why this player will not return this season.",
            )
        return cleaned


class OptionToMinorsForm(BaseTransactionForm):
    """Form for optioning players to minors"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team to option to minors"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team can be optioned"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()

    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 2,
            'placeholder': 'Additional notes...'
        }),
        label="Notes (Optional)"
    )

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["destination_level"] = "AAA"
        return cleaned_data


class PurchaseContractForm(BaseTransactionForm):
    """Form for purchasing contracts"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your minor league system to purchase their contract"
        )
    
    def get_player_queryset(self):
        """Only players from user's team who are not on the 40-man roster (eligible for contract purchase)"""
        if self.user_team:
            # Only team's players who are not on the 40-man roster
            return Player.objects.filter(
                team=self.user_team, 
                roster_40man=False,  # Not on 40-man roster
                active=True
            )
        return Player.objects.none()
    
    def get_player_level(self, player):
        """Infer the level the player is being purchased from based on their current roster status"""
        if player.roster_tripleA or player.roster_tripleA_option:
            return 'AAA'
        elif player.roster_doubleA:
            return 'AA'
        elif player.roster_singleA:
            return 'A'
        elif player.roster_nonroster:
            return 'rookie'
        elif player.roster_foreign:
            return 'foreign'
        else:
            return 'AAA'  # Default assumption
    
    contract_details = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Contract details, terms, length, etc...'
        }),
        label="Contract Details",
        help_text="Specify contract terms, length, salary, etc."
    )
    
    def clean(self):
        """Add the inferred level to the cleaned data"""
        cleaned_data = super().clean()
        player = cleaned_data.get('player')
        
        if player and hasattr(player, 'roster_tripleA'):  # It's a Player object
            # Infer and add the level information
            cleaned_data['from_level'] = self.get_player_level(player)
            cleaned_data['from_level_display'] = {
                'AAA': 'Triple-A',
                'AA': 'Double-A', 
                'A': 'Single-A',
                'rookie': 'Rookie League',
                'foreign': 'Foreign League'
            }.get(cleaned_data['from_level'], 'Unknown')
        
        return cleaned_data


class RecallOptionForm(BaseTransactionForm):
    """Form for recalling optioned players"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Bring back a player on optional assignment at Triple-A."
        )
    
    def get_player_queryset(self):
        """A recall is only a player already optioned at Triple-A."""
        if self.user_team:
            return Player.objects.filter(
                team=self.user_team,
                active=True,
                roster_tripleA_option=True,
            )
        return Player.objects.none()


class ReleasePlayerForm(BaseTransactionForm):
    """Form for releasing players"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team to release"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team can be released"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()
    
    release_type = forms.ChoiceField(
        choices=[
            ('unconditional', 'Unconditional Release'),
            ('outright', 'Outright Release'),
            ('waivers', 'Release with Waivers'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Release"
    )
    
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Reason for release...'
        }),
        label="Reason",
        help_text="Explain the reason for the release"
    )


class WaiverRequestForm(BaseTransactionForm):
    """Form for waiver requests"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team to place on waivers"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team can be placed on waivers"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()
    
    waiver_type = forms.ChoiceField(
        choices=[
            ('outright', 'Outright Waivers'),
            ('trade', 'Trade Waivers'),
            ('rule5', 'Rule 5 Waivers'),
            ('release', 'Straight Release'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Waivers"
    )

    service_class = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Service class'),
            ('under_3_outrighted', 'Under 3 years, previously outrighted'),
            ('under_3_never_outrighted', 'Under 3 years, never outrighted'),
            ('super2_to_4_171', 'Super Two through 4.171 years'),
            ('five_plus', '5 or more years'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Service class",
    )

    veteran_disposition = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Not a 5+ service-time player'),
            ('keep_40', 'If cleared, keep on the 40-man'),
            ('release', 'If cleared, release'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="5+ service time"
    )
    
    purpose = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Purpose of waiver request...'
        }),
        label="Purpose",
        help_text="Explain the purpose of placing on waivers"
    )


class WaiverClaimForm(BaseTransactionForm):
    """Form for waiver claims"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select an unowned player to claim from waivers"
        )
    
    def get_player_queryset(self):
        """Only unowned players can be claimed"""
        return Player.objects.filter(team__isnull=True, is_owned=False, active=True)
    
    claiming_from = forms.ModelChoiceField(
        queryset=Team.objects.all(),
        widget=forms.Select(attrs={'class': 'select'}),
        label="Claiming From Team"
    )
    
    claim_details = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Claim details...'
        }),
        label="Claim Details",
        help_text="Any additional details about the claim"
    )


class RestrictedListForm(BaseTransactionForm):
    """Form for restricted list transactions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team for restricted list"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team can be placed on restricted list"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()
    
    reason = forms.ChoiceField(
        choices=[
            ('RES', 'Restricted list'),
            ('DV', 'Domestic violence suspension'),
            ('PED', 'Performance-enhancing drug suspension'),
            ('Bet', 'Betting suspension'),
            ('Pat', 'Paternity leave'),
            ('FMEL', 'Family medical emergency'),
            ('Ber', 'Bereavement'),
            ('Temp', 'Pending final suspension details'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Reason for Restricted List"
    )
    
    details = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Additional details...'
        }),
        label="Details"
    )


class ForeignRetirementForm(BaseTransactionForm):
    """Form for foreign/retirement/death transactions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()
    
    transaction_reason = forms.ChoiceField(
        choices=[
            ('foreign', 'Foreign Assignment'),
            ('retirement', 'Retirement'),
            ('death', 'Death'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Transaction"
    )
    
    details = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Additional details...'
        }),
        label="Details"
    )

    source_url = forms.URLField(
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(attrs={
            "class": "input",
            "placeholder": "https://",
        }),
        label="Source URL",
        help_text="Required for a foreign-list assignment. Link to the player in that league.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("transaction_reason") == "foreign" and not cleaned.get("source_url"):
            self.add_error(
                "source_url",
                "A foreign-list assignment needs a URL showing the player is playing in a foreign league.",
            )
        return cleaned


class OffseasonTransactionForm(BaseTransactionForm):
    """Form for general offseason transactions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player (filtering depends on transaction type)"
        )
    
    def get_player_queryset(self):
        """For offseason transactions, allow both owned and unowned players"""
        if self.user_team:
            return Player.objects.filter(
                Q(team=self.user_team) |  # Team's players
                Q(team__isnull=True, is_owned=False),  # Unowned players
                active=True
            )
        return Player.objects.filter(team__isnull=True, is_owned=False, active=True)
    
    transaction_type = forms.ChoiceField(
        choices=[
            ('signing', 'Free Agent Signing'),
            ('trade', 'Trade'),
            ('extension', 'Contract Extension'),
            ('minor_league_contract', 'Minor League Contract'),
            ('invitation', 'Spring Training Invitation'),
            ('other', 'Other Offseason Transaction'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Offseason Transaction"
    )
    
    transaction_details = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 4,
            'placeholder': 'Describe the transaction details, contract terms, trade details, etc...'
        }),
        label="Transaction Details",
        help_text="Provide comprehensive details about the transaction"
    )
    
    effective_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date'
        }),
        label="Effective Date (Optional)",
        help_text="When the transaction should take effect"
    )


class LimboAssignmentForm(BaseTransactionForm):
    """Form for in limbo assignments"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player Name",
            help_text="Select a player from your team for limbo assignment"
        )
    
    def get_player_queryset(self):
        """Only players on the user's team can be assigned to limbo"""
        if self.user_team:
            return Player.objects.filter(team=self.user_team, active=True)
        return Player.objects.none()
    
    assignment_reason = forms.ChoiceField(
        choices=[
            ('pending_trade', 'Pending Trade'),
            ('investigation', 'Under Investigation'),
            ('contract_dispute', 'Contract Dispute'),
            ('other', 'Other'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Reason for Limbo Assignment"
    )
    
    details = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 3,
            'placeholder': 'Explain the circumstances...'
        }),
        label="Details",
        help_text="The club has seven days to trade or outright the player. In-limbo assignments stop after the July 31 trade deadline."
    )


class TradeProposalForm(BaseTransactionForm):
    """Clubs first, then what each club sends, then who receives each piece.

    The browser posts that deal as JSON. Two clubs or twenty use the same shape.
    """

    PIECE_KINDS = {
        "player",
        "draft_pick",
        "cash",
        "cap_space",
        "ifa_pool",
        "coverage",
        "future_considerations",
    }
    MONEY_KINDS = {"cash", "cap_space", "ifa_pool"}

    deal = forms.CharField(required=False, widget=forms.HiddenInput)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "w-full", "rows": 3}),
        label="Notes",
    )

    def clean(self):
        cleaned = super().clean()
        filing = self._pk(cleaned.get("team"))
        if filing is None:
            raise forms.ValidationError("Choose the club you are filing for.")
        try:
            payload = json.loads(cleaned.get("deal") or "")
        except json.JSONDecodeError:
            raise forms.ValidationError("Pick the clubs and add what each one sends.")
        if not isinstance(payload, dict):
            raise forms.ValidationError("Pick the clubs and add what each one sends.")

        club_ids = []
        for raw in payload.get("clubs") or []:
            club_id = self._pk(raw)
            if club_id is not None and club_id not in club_ids:
                club_ids.append(club_id)
        if filing not in club_ids:
            club_ids.insert(0, filing)
        clubs = {club.pk: club for club in Team.objects.filter(pk__in=club_ids)}
        missing = [club_id for club_id in club_ids if club_id not in clubs]
        if missing:
            raise forms.ValidationError("One of those clubs is not on the site.")
        if len(club_ids) < 2:
            raise forms.ValidationError("A trade needs at least one other club.")

        raw_pieces = payload.get("pieces") or []
        if not isinstance(raw_pieces, list) or not raw_pieces:
            raise forms.ValidationError("Add at least one piece to the pool.")
        if len(raw_pieces) > 40:
            raise forms.ValidationError("Split a deal this large into more than one trade.")

        player_ids = []
        for piece in raw_pieces:
            if isinstance(piece, dict) and piece.get("player"):
                player_ids.append(str(piece.get("player")))
        players = {
            player.pk: player
            for player in Player.objects.filter(pk__in=player_ids).select_related("team")
        }

        pieces = []
        resolved = []
        problems = []
        for index, piece in enumerate(raw_pieces, start=1):
            built, asset, error = self._piece(piece, index, clubs, players)
            if error:
                problems.append(error)
                continue
            pieces.append(built)
            resolved.append(asset)
        if problems:
            raise forms.ValidationError(problems)

        problems = problems_for_trade(resolved, club_ids)
        if problems:
            raise forms.ValidationError(problems)
        cleaned["pieces"] = pieces
        cleaned["counterparty_teams"] = [club_id for club_id in club_ids if club_id != filing]
        return cleaned

    def _piece(self, piece, index, clubs, players):
        if not isinstance(piece, dict):
            return None, None, f"Piece {index} could not be read."
        kind = (piece.get("kind") or "").strip()
        if kind not in self.PIECE_KINDS:
            return None, None, f"Piece {index} needs a type."
        giver = clubs.get(self._pk(piece.get("from")))
        getter = clubs.get(self._pk(piece.get("to")))
        if giver is None or getter is None:
            return None, None, f"Piece {index} needs the club that sends it and the club that receives it."
        if giver.pk == getter.pk:
            return None, None, f"Piece {index} cannot be sent back to the club that sends it."
        player = players.get(str(piece.get("player"))) if piece.get("player") else None
        amount = piece.get("amount")
        if amount in ("", None):
            amount = None
        else:
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                return None, None, f"Piece {index} needs a dollar amount."
        label = (piece.get("label") or "").strip()
        terms = piece.get("coverage")
        contract_terms = None
        if kind == "player":
            if player is None:
                return None, None, f"Piece {index} needs a player."
            if player.team_id != giver.pk:
                club = player.team.short_name if player.team_id else "no club"
                return None, None, f"{player.name} is on {club}, so that club has to be the one sending him."
            contract_terms = {"coverage": terms or []}
            label = player.name
        elif kind in self.MONEY_KINDS:
            if amount in (None, "") or amount <= 0:
                return None, None, f"Piece {index} needs a dollar amount."
            label = label or ASSET_LABELS.get(kind, kind)
        elif kind == "coverage":
            if player is None:
                return None, None, f"Piece {index} needs the player whose salary is covered."
            if amount in (None, "") or amount < 0:
                return None, None, f"Piece {index} needs the dollars being covered."
            try:
                year = int(piece.get("year"))
            except (TypeError, ValueError):
                return None, None, f"Piece {index} needs the year being covered."
            percent = piece.get("percent")
            contract_terms = {"year": year, "percent": percent, "salary": piece.get("salary")}
            label = f"Coverage of {player.name}, {year}"
        elif kind == "draft_pick" and not label:
            return None, None, f"Piece {index} needs a description of the pick."
        elif kind == "future_considerations" and not label:
            label = "PTBNL"
        built = {
            "asset_type": kind,
            "from_team": giver.pk,
            "to_team": getter.pk,
            "raw_label": label,
            "amount": amount,
            "contract_terms": contract_terms,
        }
        if player is not None and kind in {"player", "coverage", "future_considerations"}:
            built["player"] = player.pk
        asset = {
            "asset_type": kind,
            "from_team": giver,
            "to_team": getter,
            "player": player if kind in {"player", "coverage", "future_considerations"} else None,
            "amount": amount,
            "contract_terms": contract_terms,
            "raw_label": label,
        }
        return built, asset, None

    def _pk(self, value):
        if value is None or value == "":
            return None
        if hasattr(value, "pk"):
            return int(value.pk)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class SigningProposalForm(BaseTransactionForm):
    """Free-agent, minor-league, or extension terms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_player_field(
            label="Player",
            help_text="Choose an unowned player, or type a name if he is not in the database yet.",
        )
        self.fields['player'].required = False

    def get_player_queryset(self):
        return Player.objects.filter(team__isnull=True, active=True)

    signing_kind = forms.ChoiceField(
        choices=[
            ('mlb_signing', 'Offseason MLB signing (points)'),
            ('in_season_fa', 'In-season free agent (dollars, one year)'),
            ('minor_signing', 'Minor-league contract'),
            ('extension', 'Extension'),
            ('ifa_signing', 'IFA signing (dollars and bonus pool)'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Signing type",
    )
    player_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'input'}),
        label="Player name, if he is not listed",
    )
    years = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=8,
        widget=forms.NumberInput(attrs={'class': 'input'}),
        label="Years",
    )
    total_amount = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'input'}),
        label="Total dollars",
    )
    points = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=1,
        max_digits=6,
        widget=forms.NumberInput(attrs={'class': 'input', 'step': '0.1'}),
        label="Points",
        help_text="Offseason major-league bids are whole points, starting at 11. Minor-league bids are tenths, up to 9.9.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        label="Yearly salaries, options, and buyouts",
    )


class IFASigningForm(SigningProposalForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['signing_kind'].initial = 'ifa_signing'
        self.fields['signing_kind'].widget = forms.HiddenInput()
        self.fields['points'].widget = forms.HiddenInput()
        self.fields['total_amount'].label = "Bonus ($)"
        self.fields['total_amount'].required = True


# Map transaction types to their corresponding forms
TRANSACTION_FORM_MAP = {
    'trade': TradeProposalForm,
    'signing': SigningProposalForm,
    'ifa_signing': IFASigningForm,
    'offseason': OffseasonTransactionForm,
    'injured_list': InjuredListForm,
    'option_minors': OptionToMinorsForm,
    'purchase_contract': PurchaseContractForm,
    'recall_option': RecallOptionForm,
    'release_player': ReleasePlayerForm,
    'waiver_request': WaiverRequestForm,
    'waiver_claim': WaiverClaimForm,
    'limbo_assignment': LimboAssignmentForm,
    'restricted_list': RestrictedListForm,
    'foreign_retirement': ForeignRetirementForm,
} 