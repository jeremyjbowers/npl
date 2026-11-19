"""League directors, and the staff access the proposal review needs.

Login emails come from the Team Owners sheet. Staff status opens the director
pages. The proposal permissions are what let that same person open Review
proposals and flag a filing. A director is not made a superuser.
"""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

# Login email on the Team Owners sheet.
DIRECTOR_EMAILS = (
    "jarrett.seidler@gmail.com",
    "wes.a.french@gmail.com",
    "lvlahos343@gmail.com",
    "chrisfargis@gmail.com",
    "baldrige@gmail.com",
    "jeremyjbowers@gmail.com",
)

# The review screen and the clubs and assets shown on each proposal.
PROPOSAL_MODELS = (
    "transactionproposal",
    "transactionparty",
    "transactionasset",
)


def grant_director_staff():
    """Mark each director staff and let them review proposals.

    Returns ``(updated emails, missing emails)``. An address with no login
    account is left missing. Running this again does not add a second copy
    of the same permission.
    """
    permissions = _proposal_permissions()
    User = get_user_model()
    updated = []
    missing = []
    for email in DIRECTOR_EMAILS:
        accounts = list(User.objects.filter(email__iexact=email))
        if not accounts:
            missing.append(email)
            continue
        for user in accounts:
            if not user.is_staff:
                user.is_staff = True
                user.save(update_fields=["is_staff"])
            user.user_permissions.add(*permissions)
            updated.append(user.email)
    return updated, missing


def _proposal_permissions():
    """View and change on the proposal, its clubs, and its assets.

    Permissions are created at the end of migrate. A deploy that applies
    this during migrate, before that step, still needs the rows to exist.
    """
    permissions = []
    for model_name in PROPOSAL_MODELS:
        model = apps.get_model("npl", model_name)
        content_type, _ = ContentType.objects.get_or_create(
            app_label="npl",
            model=model._meta.model_name,
        )
        for action in ("view", "change"):
            codename = f"{action}_{model._meta.model_name}"
            name = "Can %s %s" % (action, model._meta.verbose_name_raw)
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=codename,
                defaults={"name": name},
            )
            permissions.append(permission)
    return permissions
