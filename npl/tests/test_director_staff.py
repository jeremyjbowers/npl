"""Directors can open the proposal review without becoming superusers."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase

from npl.directors import DIRECTOR_EMAILS, grant_director_staff

User = get_user_model()


class DirectorStaffTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.directors = [
            User.objects.create_user(email=email, password="secret")
            for email in DIRECTOR_EMAILS
            if email != "jeremyjbowers@gmail.com"
        ]
        self.jeremy = User.objects.create_superuser(
            email="jeremyjbowers@gmail.com", password="secret"
        )
        self.owner = User.objects.create_user(email="owner@example.com", password="secret")
        self.staff_without_review = User.objects.create_user(
            email="plain-staff@example.com", password="secret", is_staff=True
        )

    def test_directors_become_staff_and_can_review_proposals(self):
        self.client.force_login(self.staff_without_review)
        blocked = self.client.get("/admin/npl/transactionproposal/")
        self.assertEqual(blocked.status_code, 403)

        updated, missing = grant_director_staff()
        self.assertEqual(missing, [])
        self.assertCountEqual(updated, [user.email for user in self.directors] + [self.jeremy.email])

        for email in DIRECTOR_EMAILS:
            user = User.objects.get(email__iexact=email)
            self.assertTrue(user.is_staff)
            self.assertTrue(user.has_perm("npl.view_transactionproposal"))
            self.assertTrue(user.has_perm("npl.change_transactionproposal"))
            self.assertTrue(user.has_perm("npl.view_transactionparty"))
            self.assertTrue(user.has_perm("npl.change_transactionparty"))
            self.assertTrue(user.has_perm("npl.view_transactionasset"))
            self.assertTrue(user.has_perm("npl.change_transactionasset"))
            if not user.is_superuser:
                self.assertFalse(user.has_perm("npl.add_transactionproposal"))
                self.assertFalse(user.has_perm("npl.delete_transactionproposal"))

        jarrett = User.objects.get(email="jarrett.seidler@gmail.com")
        self.assertFalse(jarrett.is_superuser)
        self.client.force_login(jarrett)
        review = self.client.get("/admin/npl/transactionproposal/")
        self.assertEqual(review.status_code, 200)

        self.jeremy.refresh_from_db()
        self.assertTrue(self.jeremy.is_superuser)
        self.assertTrue(self.jeremy.is_staff)

        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_staff)
        self.client.force_login(self.owner)
        refused = self.client.get("/admin/npl/transactionproposal/")
        self.assertEqual(refused.status_code, 302)
        self.assertIn("/admin/login/", refused.url)

    def test_grant_matches_email_case_and_can_run_twice(self):
        User.objects.filter(email="jarrett.seidler@gmail.com").update(
            email="Jarrett.Seidler@gmail.com"
        )
        grant_director_staff()
        grant_director_staff()
        user = User.objects.get(email="Jarrett.Seidler@gmail.com")
        self.assertTrue(user.is_staff)
        review = Permission.objects.filter(
            codename="change_transactionproposal",
            user=user,
        )
        self.assertEqual(review.count(), 1)

    def test_a_missing_login_is_reported(self):
        User.objects.filter(email="baldrige@gmail.com").delete()
        updated, missing = grant_director_staff()
        self.assertIn("baldrige@gmail.com", missing)
        self.assertNotIn("baldrige@gmail.com", updated)
        self.assertTrue(User.objects.get(email="wes.a.french@gmail.com").is_staff)
