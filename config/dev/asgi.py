"""Dev ASGI entry: the Django site plus MCP at /mcp.

Run with: uvicorn config.dev.asgi:application --host 127.0.0.1 --port 8000
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.dev.settings")

from django.core.asgi import get_asgi_application

django_app = get_asgi_application()

from npl.mcp_app.http_app import create_site_asgi_application

application = create_site_asgi_application(django_app)
