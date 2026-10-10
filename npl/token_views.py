"""Page where a signed-in owner mints and revokes API tokens."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from npl import models
from npl.api_tokens import TokenError, generate_token, revoke

REVEAL_SESSION_KEY = "new_api_token"


@login_required
def api_tokens(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            try:
                token, raw = generate_token(
                    request.user,
                    request.POST.get("name"),
                    request.POST.get("scope"),
                )
            except TokenError as exc:
                messages.error(request, str(exc))
            else:
                request.session[REVEAL_SESSION_KEY] = {
                    "name": token.name,
                    "scope": token.get_scope_display(),
                    "secret": raw,
                }
                messages.success(request, f"Created {token.name}. Copy the token now. It will not be shown again.")
        elif action == "revoke":
            token = get_object_or_404(
                models.ApiToken,
                pk=request.POST.get("token_id"),
                user=request.user,
                revoked_at__isnull=True,
            )
            revoke(token)
            messages.success(request, f"Revoked {token.name}.")
        else:
            messages.error(request, "Choose create or revoke.")
        return redirect("api_tokens")

    revealed = request.session.pop(REVEAL_SESSION_KEY, None)
    if revealed is not None:
        request.session.modified = True
    tokens = models.ApiToken.objects.filter(user=request.user)
    return render(
        request,
        "account/api_tokens.html",
        {
            "tokens": tokens,
            "revealed": revealed,
            "read_scope": models.ApiToken.READ,
            "write_scope": models.ApiToken.READ_WRITE,
        },
    )
