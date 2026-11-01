"""Stdio MCP bridge for clients that cannot use remote HTTPS MCP.

Most owners should connect to https://YOUR-HOST/mcp with
Authorization: Bearer <token>. See documents/MCP.md.
"""

from __future__ import annotations

import os
import sys


def main(argv: list | None = None) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.dev.settings")
    import django

    django.setup()
    from npl.mcp_app.tools import build_mcp

    mcp = build_mcp(mode="remote")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
