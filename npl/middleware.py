"""Site-wide guards that run after Django has attached request.user."""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class RequireLoginMiddleware:
    """Send anonymous browsers to the login page.

    Bearer APIs under /api/ keep their own 401 handling. Auth and robots stay
    public so owners can sign in and crawlers can read Disallow.
    """

    EXEMPT_PREFIXES = (
        "/accounts/login",
        "/auth/magic-link",
        "/admin/login",
        "/api/",
        "/static/",
    )
    EXEMPT_PATHS = frozenset({"/robots.txt"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or self._is_exempt(request.path):
            return self.get_response(request)
        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

    def _is_exempt(self, path):
        if path in self.EXEMPT_PATHS:
            return True
        return any(path == prefix or path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES)
