"""Signed-in account menu, including the API keys page."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from npl import models

User = get_user_model()


class AccountNavTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="nav@example.com", password="secret")
        self.owner = models.Owner.objects.create(
            name="Nav Owner", email="nav@example.com", user=self.user
        )
        self.team = models.Team.objects.create(
            full_name="Nav Club", short_name="Navigators", abbreviation="NAV"
        )
        self.team.owners.add(self.owner)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        login = self.client.get("/accounts/login/")
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, 'href="/accounts/login/"')
        self.assertNotContains(login, "API keys")
        self.assertNotContains(login, reverse("my_api_keys"))

    def test_signed_in_account_menu_links_api_keys(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, 'aria-label="Account"')
        self.assertContains(response, "NAV ▼")
        self.assertContains(response, f'href="{reverse("my_api_keys")}"')
        self.assertContains(response, ">API keys</a>")
        self.assertContains(response, 'href="/teams/navigators/"')
        self.assertContains(response, ">My Team</a>")
        self.assertContains(response, ">Log out</a>")
        transactions = html.split("Transactions ▼", 1)[1].split("Rosters", 1)[0]
        self.assertNotIn("API keys", transactions)
        self.assertIn("nav-dropdown-end", html)
        self.assertEqual(html.count("API keys"), 2)

    def test_signed_in_user_without_a_club_still_gets_the_menu(self):
        other = User.objects.create_user(email="solo@example.com", password="secret")
        self.client.force_login(other)
        response = self.client.get("/")
        self.assertContains(response, "Account ▼")
        self.assertContains(response, f'href="{reverse("my_api_keys")}"')
        self.assertNotContains(response, ">My Team</a>")


class AsgiConnectionTests(TestCase):
    def test_production_does_not_keep_database_connections_open(self):
        settings_path = Path(__file__).resolve().parents[2] / "config" / "do_app_platform" / "settings.py"
        text = settings_path.read_text()
        self.assertIn("conn_max_age=0", text)
        self.assertNotIn("conn_max_age=60", text)
