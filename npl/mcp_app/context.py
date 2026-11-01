"""Per-request owner for in-process MCP tool calls."""

from contextvars import ContextVar

from npl.models import Owner

_current_owner: ContextVar[Owner | None] = ContextVar("npl_mcp_owner", default=None)


def set_current_owner(owner):
    return _current_owner.set(owner)


def reset_current_owner(token):
    _current_owner.reset(token)


def get_current_owner():
    return _current_owner.get()


def require_current_owner():
    owner = get_current_owner()
    if owner is None:
        raise RuntimeError("MCP call is not authenticated to an owner")
    return owner
