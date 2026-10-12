"""Players tab: login-required list, linked from the primary nav."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from npl.models import Player

User = get_user_model()


class PlayersNavTests(TestCase):
    def test_anonymous_player_list_redirects_to_login(self):
        response = self.client.get("/players/search/")
        self.assertRedirects(
            response,
            "/accounts/login/?next=/players/search/",
            fetch_redirect_response=False,
        )

    def test_logged_in_nav_links_to_player_list(self):
        Player.objects.create(
            mlb_id="000001",
            name="Pat Freeagent",
            first_name="Pat",
            last_name="Freeagent",
            team=None,
            is_owned=False,
        )
        user = User.objects.create_user(email="players@example.com", password="secret")
        client = Client()
        client.force_login(user)

        response = client.get("/players/search/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/players/search/" class="underline">Players</a>')
        self.assertContains(
            response,
            '<a href="/players/search/" class="block underline">Players</a>',
        )
        self.assertContains(
            response,
            "The list includes players who are not on a club roster.",
        )
        self.assertContains(response, "Pat Freeagent")
