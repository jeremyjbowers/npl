"""ASGI app that serves NPL MCP over Streamable HTTP."""

from __future__ import annotations

from contextlib import asynccontextmanager

from asgiref.sync import sync_to_async
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from npl.mcp_app.auth import load_token
from npl.mcp_app.context import reset_current_owner, set_current_owner
from npl.mcp_app.tools import build_mcp


class OwnerBearerMiddleware:
    """Require Authorization: Bearer npl_… and do not advertise OAuth discovery."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        auth = headers.get("authorization", "")
        raw = None
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
        if not raw:
            raw = headers.get("x-npl-token", "").strip() or None

        loaded = await sync_to_async(load_token)(raw)
        if loaded is None:
            body = b'{"error":"Unauthorized","detail":"Valid NPL API token required"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b'Bearer realm="npl"'),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        _token, owner, _team = loaded
        ctx_token = set_current_owner(owner)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_owner(ctx_token)


class SlashlessMcpMiddleware:
    """Serve Streamable HTTP at /mcp as well as /mcp/.

    Starlette Mount matches /mcp/ and /mcp/<rest>, not the exact path /mcp.
    Clients post to the URL as typed. Rewriting here keeps the request body.
    A redirect would drop the handshake.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope["path"] = "/mcp/"
            if scope.get("raw_path") == b"/mcp":
                scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


async def mcp_health(request: Request) -> Response:
    return JSONResponse(
        {
            "service": "npl-mcp",
            "phase": 1,
            "auth": "bearer",
            "transport": "streamable-http",
        }
    )


def create_mcp_http_app() -> Starlette:
    """Streamable HTTP MCP mounted at /mcp on the site ASGI app."""
    mcp = build_mcp(mode="local")
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
    mcp.settings.streamable_http_path = "/"
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True

    inner = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with inner.router.lifespan_context(inner):
            yield

    return Starlette(
        routes=[
            Route("/health", endpoint=mcp_health, methods=["GET"]),
            Mount("/", app=inner),
        ],
        middleware=[Middleware(OwnerBearerMiddleware)],
        lifespan=lifespan,
    )


def create_site_asgi_application(django_asgi_app: ASGIApp) -> Starlette:
    """Compose Django and MCP under one host."""
    mcp_app = create_mcp_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    return Starlette(
        routes=[
            Mount("/mcp", app=mcp_app),
            Mount("/", app=django_asgi_app),
        ],
        middleware=[Middleware(SlashlessMcpMiddleware)],
        lifespan=lifespan,
    )
