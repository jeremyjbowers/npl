from django import forms
from django.forms import widgets
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Team, Player, TransactionSubmission, Owner
from users.models import User
from django.db import models
from django.db.models import Q


class TransactionTypeForm(forms.Form):
    """Step 1: Choose transaction type"""
    TRANSACTION_CHOICES = [
        ('offseason', 'Offseason Transactions'),
        ('injured_list', 'Injured List'),
        ('option_minors', 'Option to Minor Leagues'),
        ('purchase_contract', 'Purchase a Contract'),
        ('recall_option', 'Recall an Option'),
        ('release_player', 'Release Player'),
        ('waiver_request', 'Waiver Request'),
        ('waiver_claim', 'Waiver Claim'),
        ('limbo_assignment', 'In Limbo Assignment'),
        ('restricted_list', 'Restricted List'),
        ('foreign_retirement', 'Foreign/Retirement/Death'),
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
        ('15-day', '15-Day IL'),
        ('60-day', '60-Day IL'),
        ('eos', 'End of Season IL'),
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
    
    retroactive_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date'
        }),
        label="Retroactive Date (Optional)",
        help_text="If this should be retroactive to a specific date"
    )


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
    
    destination_level = forms.ChoiceField(
        choices=[
            ('AAA', 'Triple-A'),
            ('AA', 'Double-A'),
            ('A', 'Single-A'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Destination Level"
    )
    
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
            help_text="Select a player from your minor league system to recall"
        )
    
    def get_player_queryset(self):
        """Only players in the user's minor league system"""
        if self.user_team:
            return Player.objects.filter(
                team=self.user_team, 
                roster_40man=False,  # Minor leaguers
                active=True
            )
        return Player.objects.none()
    
    from_level = forms.ChoiceField(
        choices=[
            ('AAA', 'Triple-A'),
            ('AA', 'Double-A'),
            ('A', 'Single-A'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Recalling From"
    )


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
            ('release', 'Release Waivers'),
            ('trade', 'Trade Waivers'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        label="Type of Waivers"
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
            ('suspension', 'Suspension'),
            ('personal', 'Personal Reasons'),
            ('other', 'Other'),
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
        help_text="Provide context for the limbo assignment"
    )


# Map transaction types to their corresponding forms
TRANSACTION_FORM_MAP = {
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