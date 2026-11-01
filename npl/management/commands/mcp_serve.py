from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run the NPL stdio MCP bridge (requires NPL_API_URL and NPL_API_TOKEN). "
        "Owners who can set a remote MCP URL should use https://YOUR-HOST/mcp instead."
    )

    def handle(self, *args, **options):
        from npl.mcp_app.server import main

        main()
