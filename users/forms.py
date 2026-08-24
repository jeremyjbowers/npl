from django import forms
from django.core.exceptions import ValidationError

from allauth.account.forms import SignupForm

from users.models import User
from users.names import DOMAIN_IN_NAME_MESSAGE, name_contains_domain


def _clean_person_name(value):
    if name_contains_domain(value):
        raise ValidationError(DOMAIN_IN_NAME_MESSAGE, code="domain_in_name")
    return value


class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = "__all__"

    def clean_first_name(self):
        return _clean_person_name(self.cleaned_data.get("first_name", ""))

    def clean_last_name(self):
        return _clean_person_name(self.cleaned_data.get("last_name", ""))


class SpamResistantSignupForm(SignupForm):
    """Reject first/last names that contain domains, even if posted as extra fields."""

    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    def clean_first_name(self):
        return _clean_person_name(self.cleaned_data.get("first_name", ""))

    def clean_last_name(self):
        return _clean_person_name(self.cleaned_data.get("last_name", ""))

    def clean(self):
        cleaned = super().clean()
        for field in ("first_name", "last_name"):
            value = (cleaned or {}).get(field) or self.data.get(field) or ""
            if name_contains_domain(value):
                self.add_error(field, DOMAIN_IN_NAME_MESSAGE)
        return cleaned
