"""Bearer auth for the NPL MCP JSON API."""

from functools import wraps

from django.http import JsonResponse

from npl import models
from npl.api_tokens import authenticate, mark_used


def extract_bearer_token(request):
    """Return the raw token from Authorization: Bearer or X-NPL-Token."""
    auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.META.get("HTTP_X_NPL_TOKEN", "") or ""
    return header.strip() or None


def load_token(raw):
    """Return (token, owner, team) for a live key, or None."""
    token = authenticate(raw)
    if token is None:
        return None
    mark_used(token)
    owner = models.Owner.objects.filter(user_id=token.user_id).first()
    team = models.Team.objects.filter(owners=owner).first() if owner else None
    return token, owner, team


def require_api_token(view_func=None, *, write=False):
    """Require a live API key. write=True refuses a read-only key."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            loaded = load_token(extract_bearer_token(request))
            if loaded is None:
                return JsonResponse(
                    {"error": "Unauthorized", "detail": "Valid NPL API token required"},
                    status=401,
                )
            token, owner, team = loaded
            if write and not token.allows_write:
                return JsonResponse(
                    {"error": "Forbidden", "detail": "This API key is read-only"},
                    status=403,
                )
            request.api_token = token
            request.mcp_owner = owner
            request.mcp_team = team
            return fn(request, *args, **kwargs)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator
