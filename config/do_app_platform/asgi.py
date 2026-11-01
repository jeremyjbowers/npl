"""App Platform ASGI entry: the Django site plus MCP at /mcp.

Run with uvicorn so owners can connect an MCP client over HTTPS.
The JSON API under /api/mcp/v1/ also works on the WSGI app.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.do_app_platform.settings")

from django.core.asgi import get_asgi_application

django_app = get_asgi_application()

from npl.mcp_app.http_app import create_site_asgi_application

application = create_site_asgi_application(django_app)
