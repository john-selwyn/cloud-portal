from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail, signing
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .customer_security import (EMAIL_SALT, confirm_email, prepare_email, request_allowed,
                                send_verification, verified_email)
from .models import AccountRequestLimit, CustomerEmail

TEST_MAIL = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@override_settings(CUSTOMER_EMAIL_ENABLED=True, CUSTOMER_PUBLIC_ORIGIN="https://portal.example.invalid",
                   DEFAULT_FROM_EMAIL="accounts@example.invalid", MAILERS=TEST_MAIL,
                   CUSTOMER_REQUIRE_EMAIL_VERIFICATION=False)
class CustomerAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "Test-Customer-Password-91237"
        cls.buyer = User.objects.create_user("buyer", email="buyer@example.invalid", password=cls.password)
        cls.other = User.objects.create_user("other", email="other@example.invalid", password=cls.password)
        cls.staff = User.objects.create_user("staff", email="staff@example.invalid", password=cls.password, is_staff=True)

    def setUp(self):
        self.client.force_login(self.buyer)

    def pending(self, user=None, email="new@example.invalid"):
        user = user or self.buyer
        with transaction.atomic():
            row = prepare_email(user, email)
        token = signing.dumps({"id": row.pk, "nonce": str(row.nonce)}, salt=EMAIL_SALT)
        return row, token

    def signup(self, **extra):
        self.client.logout()
        return self.client.post(reverse("register"), {
            "username": "newbuyer", "full_name": "New Buyer", "email": "New@Example.invalid",
            "password1": self.password, "password2": self.password,
            "company": "Example Company", "phone": "+63 900 123 4567", **extra})

    def reset_url(self, user=None):
        user = user or self.buyer
        return reverse("password_reset_confirm", args=[urlsafe_base64_encode(force_bytes(user.pk)),
                                                      default_token_generator.make_token(user)])

    def test_signup_normalizes_email_and_saves_profile_without_roles(self):
        response = self.signup(is_staff="on", is_superuser="on", user_id=self.staff.pk)
        self.assertRedirects(response, reverse("account"))
        user = User.objects.get(username="newbuyer")
        self.assertEqual(user.email, "new@example.invalid")
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(user.customer_profile.company, "Example Company")
        self.assertEqual(user.customer_profile.phone, "+63 900 123 4567")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://portal.example.invalid/accounts/email/verify/", mail.outbox[0].body)

    def test_signup_rejects_duplicate_and_staff_email_case_insensitively(self):
        for email in ["BUYER@example.invalid", "STAFF@EXAMPLE.invalid"]:
            self.assertContains(self.signup(email=email), "This email address cannot be used")
        self.assertFalse(User.objects.filter(username="newbuyer").exists())

    def test_signup_duplicate_username_and_weak_password_preserve_no_account(self):
        self.assertContains(self.signup(username="buyer"), "already exists")
        self.assertEqual(self.signup(password1="123", password2="123").status_code, 200)
        self.assertFalse(User.objects.filter(username="newbuyer").exists())

    @override_settings(CUSTOMER_REQUIRE_EMAIL_VERIFICATION=True)
    def test_required_verification_gates_services_but_allows_account_and_password(self):
        self.assertRedirects(self.signup(), reverse("email_verification_needed"))
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("email_verification_needed"))
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 200)
        self.assertRedirects(self.client.post(reverse("order_confirm")), reverse("email_verification_needed"))
        url = re.search(r"https://[^\s]+", mail.outbox[0].body).group().replace("https://portal.example.invalid", "")
        self.client.get(url)
        self.client.post(url)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_legacy_customer_not_locked_out(self):
        self.assertFalse(self.buyer.customer_profile.email_verification_required)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertFalse(verified_email(self.buyer))

    def test_profile_edit_cannot_change_email_username_or_another_customer(self):
        self.client.post(reverse("account"), {"full_name": "Updated Buyer", "company": "New Company",
                         "phone": "123", "user": self.other.pk, "email": "injected@example.invalid", "is_staff": "on"})
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, "buyer@example.invalid")
        self.assertFalse(self.buyer.is_staff)
        self.assertEqual(self.buyer.customer_profile.full_name, "Updated Buyer")
        self.assertEqual(self.other.customer_profile.full_name, "other")

    def test_email_change_requires_password_and_waits_for_confirmation(self):
        data = {"email": "replacement@example.invalid", "current_password": "wrong"}
        self.assertContains(self.client.post(reverse("change_email"), data), "current password was incorrect")
        self.assertFalse(CustomerEmail.objects.exists())
        data["current_password"] = self.password
        self.assertRedirects(self.client.post(reverse("change_email"), data), reverse("account"))
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, "buyer@example.invalid")
        self.assertEqual(mail.outbox[0].to, ["replacement@example.invalid"])

    def test_verify_get_does_not_change_email_post_consumes_once(self):
        row, token = self.pending()
        url = reverse("verify_email", args=[token])
        response = self.client.get(url)
        self.assertContains(response, "Confirm your email address")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, "buyer@example.invalid")
        self.assertContains(self.client.post(url), "Email confirmed")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, row.email)
        self.assertTrue(verified_email(self.buyer))
        self.assertFalse(confirm_email(token, apply=True))

    def test_email_token_tamper_expiry_resend_and_cancel(self):
        _, token = self.pending()
        self.assertFalse(confirm_email(token + "bad", apply=True))
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 3700):
            self.assertFalse(confirm_email(token, apply=True))
        self.pending(email="second@example.invalid")
        self.assertFalse(confirm_email(token, apply=True))
        _, replacement = self.pending()
        self.assertRedirects(self.client.post(reverse("cancel_email_change")), reverse("account"))
        self.assertFalse(confirm_email(replacement, apply=True))

    def test_password_change_or_external_email_edit_invalidates_email_token(self):
        _, token = self.pending()
        self.buyer.set_password("Different-Customer-Password-7890")
        self.buyer.save()
        self.assertFalse(confirm_email(token, apply=True))
        _, token = self.pending()
        self.buyer.email = "externally-edited@example.invalid"
        self.buyer.save()
        self.assertFalse(confirm_email(token, apply=True))

    def test_email_claim_blocks_another_customer_and_releases_expired_request(self):
        self.pending()
        with self.assertRaises(ValueError):
            self.pending(self.other)
        CustomerEmail.objects.update(requested_at=timezone.now() - timedelta(hours=2))
        row, token = self.pending(self.other)
        self.assertEqual(row.user_id, self.other.pk)
        self.assertTrue(confirm_email(token, apply=True))

    def test_disabled_or_staff_accounts_cannot_confirm(self):
        _, token = self.pending()
        self.buyer.is_active = False
        self.buyer.save()
        self.assertFalse(confirm_email(token, apply=True))
        self.buyer.is_active, self.buyer.is_staff = True, True
        self.buyer.save()
        self.assertFalse(confirm_email(token, apply=True))

    def test_login_accepts_email_and_username_and_blocks_staff(self):
        self.client.logout()
        for identifier in ["BUYER@EXAMPLE.invalid", "buyer"]:
            self.assertRedirects(self.client.post(reverse("login"), {"username": identifier, "password": self.password}), reverse("dashboard"))
            self.client.logout()
        self.assertContains(self.client.post(reverse("login"), {"username": "staff@example.invalid", "password": self.password}), "Management Portal")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ambiguous_historical_email_cannot_login_or_recover(self):
        self.other.email = self.buyer.email.upper()
        self.other.save()
        self.client.logout()
        self.assertEqual(self.client.post(reverse("login"), {"username": self.buyer.email, "password": self.password}).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.post(reverse("password_reset"), {"email": self.buyer.email})
        self.assertEqual(len(mail.outbox), 0)
        self.assertRedirects(self.client.post(reverse("login"), {"username": self.buyer.username, "password": self.password}), reverse("dashboard"))

    def test_password_change_keeps_current_session_revokes_other_session_and_pending_token(self):
        other_browser = Client()
        other_browser.force_login(self.buyer)
        _, token = self.pending()
        new_password = "Replacement-Customer-Password-4567"
        self.assertRedirects(self.client.post(reverse("password_change"), {"old_password": self.password,
                            "new_password1": new_password, "new_password2": new_password}), reverse("password_change_done"))
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)
        self.assertEqual(other_browser.get(reverse("account")).status_code, 302)
        self.assertFalse(confirm_email(token, apply=True))

    def test_recovery_response_same_for_customer_unknown_staff_inactive(self):
        self.client.logout()
        inactive = User.objects.create_user("inactive", email="inactive@example.invalid", password=self.password, is_active=False)
        for email in [self.buyer.email, "missing@example.invalid", self.staff.email, inactive.email]:
            response = self.client.post(reverse("password_reset"), {"email": email})
            self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.buyer.email])
        self.assertIn("https://portal.example.invalid/accounts/reset/", mail.outbox[0].body)
        self.assertNotIn("testserver", mail.outbox[0].body)

    def test_password_reset_consumed_once_and_invalidates_sessions(self):
        self.client.logout()
        url = self.reset_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(url.split("/")[-2], response.url)
        self.assertContains(self.client.get(response.url), "Choose a new password")
        new_password = "Recovered-Customer-Password-6543"
        self.assertRedirects(self.client.post(response.url, {"new_password1": new_password,
                            "new_password2": new_password}), reverse("password_reset_complete"))
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.check_password(new_password))
        self.assertContains(self.client.get(url), "reset link is unavailable")

    def test_direct_reset_token_cannot_change_staff_password(self):
        self.client.logout()
        self.assertContains(self.client.get(self.reset_url(self.staff)), "reset link is unavailable")

    def test_reset_expiry_and_role_change_invalidate_confirm(self):
        self.client.logout()
        url = self.reset_url()
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertContains(self.client.get(url), "reset link is unavailable")
        response = self.client.get(url)
        self.buyer.is_staff = True
        self.buyer.save()
        self.assertContains(self.client.post(response.url, {"new_password1": "Replacement-Password-98127",
                            "new_password2": "Replacement-Password-98127"}), "reset link is unavailable")

    @override_settings(CUSTOMER_EMAIL_ENABLED=False)
    def test_mail_disabled_explicit_no_mail_and_no_email_change(self):
        self.assertContains(self.client.get(reverse("password_reset")), "not available yet")
        self.client.post(reverse("password_reset"), {"email": self.buyer.email})
        self.client.post(reverse("change_email"), {"email": "new@example.invalid", "current_password": self.password})
        self.client.post(reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(CustomerEmail.objects.exists())
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

    def test_smtp_failure_does_not_publish_token_or_exception(self):
        row, _ = self.pending()
        with patch("portal.customer_security.send_mail", side_effect=RuntimeError("private-detail")):
            with self.assertLogs("portal.customer_security", level="WARNING") as logs:
                self.assertFalse(send_verification(row))
        self.assertNotIn("private-detail", "".join(logs.output))

    def test_csrf_protects_email_password_and_verification_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        _, token = self.pending()
        for name, args in [("change_email", []), ("resend_verification", []), ("cancel_email_change", []),
                           ("password_change", []), ("verify_email", [token]), ("password_reset", [])]:
            self.assertEqual(client.post(reverse(name, args=args)).status_code, 403, name)
        self.assertFalse(verified_email(self.buyer))

    def test_staff_cannot_use_customer_security_with_replayed_cookie(self):
        self.client.force_login(self.staff)
        for name in ["change_email", "resend_verification", "cancel_email_change", "password_change", "password_change_done"]:
            self.assertEqual(self.client.post(reverse(name)).status_code, 403)

    def test_login_rate_limit_shared_across_sessions_and_does_not_store_identifiers(self):
        client = Client()
        request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.40")
        for _ in range(30):
            self.assertTrue(request_allowed(request, "login", self.buyer.username, limit=30, seconds=900))
        response = client.post(reverse("login"), {"username": self.buyer.username, "password": self.password}, REMOTE_ADDR="192.0.2.40")
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertFalse(AccountRequestLimit.objects.filter(key__contains="buyer").exists())

    def test_reset_and_resend_rate_limits_bound_email_volume(self):
        for _ in range(7):
            self.client.post(reverse("password_reset"), {"email": self.buyer.email})
        self.assertEqual(len(mail.outbox), 5)
        for _ in range(7):
            self.client.post(reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 10)

    def test_request_limits_expire_and_cleanup_retains_accounts(self):
        from django.core.management import call_command
        request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.40")
        self.assertTrue(request_allowed(request, "sample", limit=1))
        self.assertFalse(request_allowed(request, "sample", limit=1))
        AccountRequestLimit.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertTrue(request_allowed(request, "sample", limit=1))
        row, token = self.pending()
        self.assertTrue(confirm_email(token, apply=True))
        CustomerEmail.objects.filter(pk=row.pk).update(requested_at=timezone.now()-timedelta(hours=2))
        call_command("cleanup_account_requests", verbosity=0)
        self.assertTrue(CustomerEmail.objects.filter(pk=row.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.buyer.pk).exists())

    def test_untrusted_proxy_header_cannot_bypass_ip_limit(self):
        for number in range(2):
            request = RequestFactory().post('/', REMOTE_ADDR='192.0.2.40', HTTP_X_REAL_IP=f'198.51.100.{number}')
            self.assertEqual(request_allowed(request, 'proxy-test', limit=1), number == 0)

    @override_settings(CUSTOMER_TRUSTED_PROXY_IPS=['127.0.0.1'])
    def test_trusted_proxy_distinguishes_clients_and_rejects_malformed_ip(self):
        for address in ['198.51.100.1', '198.51.100.2']:
            request = RequestFactory().post('/', REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP=address)
            self.assertTrue(request_allowed(request, 'proxy-test', limit=1))
            self.assertFalse(request_allowed(request, 'proxy-test', limit=1))
        for invalid in ['198.51.100.3, 198.51.100.4', 'invalid']:
            request = RequestFactory().post('/', REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP=invalid)
            # Invalid proxy headers fall back to the proxy's address, not a new key.
            self.assertEqual(request_allowed(request, 'proxy-invalid', limit=1), invalid.startswith('198.'))


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL")
class CustomerAccountConcurrencyTests(TransactionTestCase):
    def test_parallel_requests_share_one_atomic_limit(self):
        def attempt(_):
            close_old_connections()
            try:
                request = RequestFactory().post('/', REMOTE_ADDR='192.0.2.80')
                return request_allowed(request, 'parallel-test', limit=2)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(results.count(True), 2)
        self.assertEqual(AccountRequestLimit.objects.get().count, 4)

    def test_two_accounts_cannot_claim_same_email(self):
        users = [User.objects.create_user(f"buyer-{i}", email=f"buyer-{i}@example.invalid", password="Test-Password-78326") for i in range(2)]

        def claim(pk):
            close_old_connections()
            try:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=pk)
                    prepare_email(user, "reserved@example.invalid")
                return "claimed"
            except (ValueError, IntegrityError):
                return "refused"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, [user.pk for user in users]))
        self.assertEqual(sorted(results), ["claimed", "refused"])
        self.assertEqual(CustomerEmail.objects.filter(email="reserved@example.invalid").count(), 1)
