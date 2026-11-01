"""Page where a signed-in owner generates and revokes API keys."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from npl import models, utils
from npl.api_tokens import TokenError, generate_token, revoke


def _own_token(user, raw_id):
    """This user's key, or 404 if the id is missing or someone else's."""
    if raw_id in (None, ""):
        raise Http404("API key not found")
    try:
        return models.ApiToken.objects.get(pk=raw_id, user=user)
    except (models.ApiToken.DoesNotExist, ValueError, ValidationError):
        raise Http404("API key not found")


@never_cache
@login_required
def api_tokens(request):
    context = utils.build_context(request)
    owner = context["owner"]
    context["needs_owner"] = owner is None
    context["mcp_url"] = request.build_absolute_uri("/mcp")

    if owner is None:
        if request.method == "POST":
            return HttpResponseForbidden("This account is not linked to an owner.")
        context["tokens"] = []
        return render(request, "account/api_tokens.html", context)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            scope = request.POST.get("scope") or ""
            name = (request.POST.get("name") or "").strip()
            if scope not in {models.ApiToken.READ, models.ApiToken.READ_WRITE}:
                messages.error(request, "Pick a read or read-write key.")
            else:
                try:
                    generate_token(request.user, name, scope)
                except TokenError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "API key created. It is listed below.")
        elif action == "revoke":
            token = _own_token(request.user, request.POST.get("token_id"))
            if token.revoked_at is None:
                revoke(token)
                messages.success(request, "API key revoked.")
            else:
                messages.success(request, "That API key is already revoked.")
        else:
            messages.error(request, "Choose create or revoke.")
        return redirect(request.path)

    tokens = list(models.ApiToken.objects.filter(user=request.user))
    active = next((token for token in tokens if token.is_active and token.token_secret), None)
    context.update({
        "tokens": tokens,
        "mcp_secret": active.token_secret if active else "",
        "read_scope": models.ApiToken.READ,
        "write_scope": models.ApiToken.READ_WRITE,
    })
    return render(request, "account/api_tokens.html", context)
