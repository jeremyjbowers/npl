from django.core.exceptions import ValidationError

from allauth.account.adapter import DefaultAccountAdapter

from users.names import DOMAIN_IN_NAME_MESSAGE, name_contains_domain


class AccountAdapter(DefaultAccountAdapter):
    """League accounts are created by admins, not public signup."""

    def is_open_for_signup(self, request):
        return False

    def save_user(self, request, user, form, commit=True):
        data = getattr(form, "cleaned_data", None) or {}
        post = getattr(request, "POST", None) or {}
        errors = {}
        for field in ("first_name", "last_name"):
            value = data.get(field) or post.get(field) or ""
            if name_contains_domain(value):
                errors[field] = DOMAIN_IN_NAME_MESSAGE
        if errors:
            raise ValidationError(errors)
        return super().save_user(request, user, form, commit=commit)
