"""Bearer tokens for the transaction API and MCP tools."""

import hashlib
import secrets

from django.utils import timezone

from npl import models

TOKEN_PREFIX = "npl_"
MAX_ACTIVE_TOKENS = 25


class TokenError(Exception):
    pass


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token(user, name, scope):
    name = (name or "").strip()
    if not name:
        raise TokenError("Name the token so you can tell your agents apart.")
    if len(name) > 80:
        raise TokenError("Token names can be at most 80 characters.")
    if scope not in {models.ApiToken.READ, models.ApiToken.READ_WRITE}:
        raise TokenError("Choose read, or read and write.")
    active = models.ApiToken.objects.filter(user=user, revoked_at__isnull=True).count()
    if active >= MAX_ACTIVE_TOKENS:
        raise TokenError("Revoke an old token before creating another.")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = models.ApiToken.objects.create(
        user=user,
        name=name,
        token_prefix=raw[:12],
        token_hash=hash_token(raw),
        scope=scope,
    )
    return token, raw


def authenticate(raw):
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    token = (
        models.ApiToken.objects.filter(token_hash=hash_token(raw.strip()), revoked_at__isnull=True)
        .select_related("user")
        .first()
    )
    if token is None or not token.user.is_active:
        return None
    return token


def mark_used(token):
    models.ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())


def revoke(token):
    if token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at", "last_modified"])
    return token
