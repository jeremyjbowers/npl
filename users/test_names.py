import unittest

from users.names import name_contains_domain


class NameContainsDomainTests(unittest.TestCase):
    def test_spam_first_names_from_admin(self):
        self.assertTrue(
            name_contains_domain("Claim Your Authentic Money jolpo.kesug.com 7f GJ")
        )
        self.assertTrue(
            name_contains_domain("Unlock Your VIP Reward riooep.wuaze.com js GJ")
        )

    def test_spam_last_names_from_admin(self):
        self.assertTrue(
            name_contains_domain("Access Your Certified Reward riooep.wuaze.com XB GJ")
        )
        self.assertTrue(
            name_contains_domain("Access Your Craps Bonus jrert.great-site.net Vm GJ")
        )

    def test_plain_com_tld(self):
        self.assertTrue(name_contains_domain("spam.com"))
        self.assertTrue(name_contains_domain("SPAM.COM"))
        self.assertTrue(name_contains_domain("visit example.com now"))

    def test_urls_and_emails(self):
        self.assertTrue(name_contains_domain("https://evil.com/bonus"))
        self.assertTrue(name_contains_domain("www.spam.net"))
        self.assertTrue(name_contains_domain("bots@gmail.com"))

    def test_real_names_are_allowed(self):
        for name in (
            "Jeremy",
            "O'Connor",
            "St. John",
            "J.R.",
            "Mary-Jane",
            "José",
            "Anne Marie",
            "",
            None,
        ):
            self.assertFalse(
                name_contains_domain(name),
                f"{name!r} should be allowed",
            )


if __name__ == "__main__":
    unittest.main()
