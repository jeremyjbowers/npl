"""Magic-link lifetime. These links should last as long as the signer allows."""

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from sesame.utils import get_token, get_user

from users.models import User


class MagicLinkTests(TestCase):
    def test_link_and_session_use_the_longest_practical_lifetime(self):
        sixty_years = 60 * 60 * 24 * 365 * 60
        self.assertGreaterEqual(settings.SESAME_MAX_AGE, sixty_years)
        self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 24 * 400)
        self.assertFalse(settings.SESAME_ONE_TIME)
        self.assertFalse(settings.SESAME_INVALIDATE_ON_PASSWORD_CHANGE)
        self.assertFalse(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

        user = User.objects.create_user(email="owner@example.com")
        self.assertEqual(get_user(get_token(user)).pk, user.pk)

    def test_login_page_does_not_promise_a_30_day_link(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "60 years")
        self.assertNotContains(response, "30 days")

    def test_login_matches_email_without_regard_to_case(self):
        User.objects.create_user(email="bret.sayre@gmail.com")
        with patch("npl.auth.MailgunEmailer.send_email") as send:
            response = self.client.post("/accounts/login/", {"email": "Bret.Sayre@gmail.com"})
        self.assertEqual(response.status_code, 302)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "bret.sayre@gmail.com")
