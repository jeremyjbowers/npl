"""Detect website domains in person names.

Spam signups fill first/last name with promo copy plus a domain, e.g.
"Claim Your Authentic Money jolpo.kesug.com 7f GJ". Real names never
contain a TLD like .com, a URL, or an email address.
"""

import re

DOMAIN_IN_NAME_MESSAGE = (
    "Names cannot contain website addresses or domain names."
)

# TLDs that never belong in a person's name. .com/.net are the ones showing
# up in current bot traffic; the rest are common spam/generic TLDs.
NAME_TLDS = (
    "com",
    "net",
    "org",
    "info",
    "biz",
    "xyz",
    "online",
    "site",
    "club",
    "top",
    "icu",
    "shop",
    "store",
    "app",
    "dev",
    "io",
    "cc",
    "tv",
    "cloud",
    "space",
    "fun",
    "live",
    "news",
    "click",
    "link",
    "work",
    "pro",
    "vip",
    "edu",
    "gov",
    "mil",
    "wang",
    "win",
    "loan",
    "download",
    "stream",
    "gdn",
    "gq",
    "cf",
    "ga",
    "ml",
    "tk",
)

_TLD_ALTERNATION = "|".join(
    sorted(NAME_TLDS, key=len, reverse=True)
)

# Match a leading-dot TLD as its own token so "St. John" and "J.R." pass.
NAME_TLD_RE = re.compile(
    rf"\.(?:{_TLD_ALTERNATION})\b",
    re.IGNORECASE,
)
URL_RE = re.compile(r"(?:https?://|\bwww\.)", re.IGNORECASE)
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")


def name_contains_domain(value):
    """Return True if a first/last name contains a domain, URL, or email."""
    if not value:
        return False
    text = str(value)
    return bool(
        NAME_TLD_RE.search(text)
        or URL_RE.search(text)
        or EMAIL_RE.search(text)
    )


def domain_in_name_q():
    """Django Q object matching users whose names look like they contain a domain.

    Imported lazily so this module can be unit-tested without Django.
    """
    from django.db.models import Q

    query = Q()
    for tld in NAME_TLDS:
        needle = f".{tld}"
        query |= Q(first_name__icontains=needle) | Q(last_name__icontains=needle)
    for needle in ("http://", "https://", "www.", "@"):
        query |= Q(first_name__icontains=needle) | Q(last_name__icontains=needle)
    return query
