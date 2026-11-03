"""Anonymous browsers are sent to the login page."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from npl import models

User = get_user_model()


class RequireLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="gate@example.com", password="secret")
        owner = models.Owner.objects.create(
            name="Gate Owner", email="gate@example.com", user=self.user
        )
        team = models.Team.objects.create(
            full_name="Gate Club", short_name="Gates", abbreviation="GAT"
        )
        team.owners.add(owner)

    def test_anonymous_pages_redirect_to_login(self):
        for path in (
            "/",
            "/teams/gates/",
            "/players/search/",
            "/auctions/",
            "/transactions/",
            "/transactions/trades/",
            "/my/api-keys/",
            "/pages/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)
                self.assertIn(f"next={path}", response.url)

    def test_login_and_robots_stay_public(self):
        login = self.client.get("/accounts/login/")
        self.assertEqual(login.status_code, 200)
        robots = self.client.get("/robots.txt")
        self.assertEqual(robots.status_code, 200)
        self.assertIn(b"Disallow: /", robots.content)

    def test_api_without_a_token_still_returns_json_401(self):
        response = self.client.get("/api/v1/transactions/kinds/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")

    def test_signed_in_user_can_open_the_homepage(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "THE NPL")
