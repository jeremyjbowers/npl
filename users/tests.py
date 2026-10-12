from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from users.models import User
from users.names import DOMAIN_IN_NAME_MESSAGE


class UserNameValidationTests(SimpleTestCase):
    def test_rejects_domain_in_first_name(self):
        user = User(
            email="bot@example.com",
            first_name="Claim Your Money jolpo.kesug.com GJ",
            last_name="Wells",
        )
        with self.assertRaises(ValidationError) as ctx:
            user.clean()
        self.assertIn("first_name", ctx.exception.message_dict)
        self.assertEqual(
            ctx.exception.message_dict["first_name"],
            [DOMAIN_IN_NAME_MESSAGE],
        )

    def test_rejects_domain_in_last_name(self):
        user = User(
            email="bot@example.com",
            first_name="Blake",
            last_name="Access Your Bonus great-site.net GJ",
        )
        with self.assertRaises(ValidationError) as ctx:
            user.clean()
        self.assertIn("last_name", ctx.exception.message_dict)

    def test_allows_ordinary_names(self):
        user = User(email="owner@example.com", first_name="St. John", last_name="O'Connor")
        user.clean()
