"""The engine client refuses to invent a game when nothing is listening."""

from django.test import SimpleTestCase, override_settings

from npl.engine_client import EngineUnavailable, health


class EngineClientTests(SimpleTestCase):
    @override_settings(ENGINE_URL="")
    def test_health_without_a_url(self):
        with self.assertRaises(EngineUnavailable):
            health()
