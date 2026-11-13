"""The HTTP client for the vendored engine in ``engine/``.

The engine plays one game. Django sends the whole state, a call, and a seed,
and gets back one plate appearance. NPL does not sit a manager in that loop.
The weekly card is the instruction, the computer manager makes the calls, and
the box score is what gets kept.

Run it with ``cargo run --manifest-path engine/Cargo.toml --bin serve``. It
listens on ``ENGINE_URL``, port 41731 when ``PORT`` is unset.
"""

import secrets

import requests
from django.conf import settings


CONNECT_TIMEOUT_SECONDS = 2
READ_TIMEOUT_SECONDS = 10


class EngineError(Exception):
    """The engine answered and refused the request."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class EngineUnavailable(EngineError):
    """ENGINE_URL is unset, or the process did not answer."""


def new_seed():
    """63 bits, so the seed also fits a signed 64-bit column."""
    return secrets.randbits(63)


def health():
    return _get("/health")


def start(fixture, seed):
    """Open a game. Returns the opening state."""
    return _post("/start", {"fixture": fixture, "seed": seed})["state"]


def step(state, seed, call=None, runners=None, league_spd=None):
    """Resolve one plate appearance. The same inputs always return the same play."""
    payload = {"state": state, "call": call, "seed": seed}
    if runners is not None:
        payload["runners"] = runners
    if league_spd is not None:
        payload["league_spd"] = league_spd
    return _post("/step", payload)


def bring_in_pitcher(state, pitcher, seed):
    return _post("/pitcher", {"state": state, "pitcher": pitcher, "seed": seed})["state"]


def substitute(state, side, index, batter, role=None):
    payload = {"state": state, "side": side, "index": index, "batter": batter}
    if role is not None:
        payload["role"] = role
    return _post("/substitute", payload)["state"]


def set_positions(state, side, changes):
    return _post("/positions", {"state": state, "side": side, "changes": changes})["state"]


def matchup(state):
    return _post("/matchup", {"state": state})


def _base_url():
    url = getattr(settings, "ENGINE_URL", None)
    if not url:
        raise EngineUnavailable("ENGINE_URL is not set, so the engine cannot be reached.")
    return url.rstrip("/")


def _get(path):
    url = _base_url() + path
    return _send(url, lambda: requests.get(url, timeout=_timeouts()))


def _post(path, payload):
    url = _base_url() + path
    return _send(url, lambda: requests.post(url, json=payload, timeout=_timeouts()))


def _timeouts():
    return (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)


def _send(url, request):
    try:
        response = request()
    except requests.Timeout as err:
        raise EngineUnavailable(f"The engine at {url} did not answer in time: {err}") from err
    except requests.ConnectionError as err:
        raise EngineUnavailable(f"The engine at {url} is down or unreachable: {err}") from err
    if response.status_code >= 500:
        raise EngineUnavailable(
            f"The engine at {url} failed with HTTP {response.status_code}: {response.text[:500]}",
            status=response.status_code,
        )
    if response.status_code >= 400:
        try:
            message = response.json()["error"]
        except (ValueError, KeyError, TypeError):
            message = response.text[:500]
        raise EngineError(
            f"The engine refused {url} with HTTP {response.status_code}: {message}",
            status=response.status_code,
        )
    return response.json()
