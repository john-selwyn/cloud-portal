from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Customer, Order, VPSPlan
from .test_management import force_staff_login


class AccountSeparationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "Strong-Portal-Test-9132"
        cls.staff = User.objects.create_user("operator", password=cls.password, is_staff=True)
        cls.root = User.objects.create_superuser("owner", password=cls.password, email="owner@example.invalid")
        cls.buyer = User.objects.create_user("buyer", password=cls.password)

    def staff_url(self, action="changelist", pk=None):
        return reverse(f"management:auth_user_{action}", args=[pk] if pk else [])

    def login(self, user, staff=False, client=None):
        return (client or self.client).post(reverse("management:login" if staff else "login"), {
            "username": user.username, "password": self.password,
        })

    def test_new_staff_and_superuser_do_not_create_customer_profiles(self):
        self.assertFalse(Customer.objects.filter(user__in=[self.staff, self.root]).exists())
        self.assertTrue(Customer.objects.filter(user=self.buyer).exists())

    def test_customer_login_accepts_customer_and_rejects_staff_credentials(self):
        self.assertEqual(self.login(self.buyer).status_code, 302)
        self.client.logout()
        response = self.login(self.staff)
        self.assertContains(response, "Staff accounts sign in at the Management Portal.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_management_login_rejects_customer_credentials(self):
        self.assertEqual(self.login(self.buyer, staff=True).status_code, 200)
        self.assertEqual(self.client.get(reverse("management:index")).status_code, 302)

    def test_both_accounts_can_sign_in_in_one_browser(self):
        self.login(self.buyer)
        customer_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.login(self.staff, staff=True)
        self.assertEqual(self.client.cookies[settings.SESSION_COOKIE_NAME].value, customer_cookie)
        self.assertNotEqual(self.client.cookies["management_sessionid"].value, customer_cookie)
        customer_page = self.client.get(reverse("dashboard"))
        staff_page = self.client.get(reverse("management:index"))
        self.assertEqual(customer_page.wsgi_request.user.pk, self.buyer.pk)
        self.assertEqual(staff_page.wsgi_request.user.pk, self.staff.pk)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, staff_page.cookies)

    def test_staff_logout_preserves_customer_session(self):
        self.login(self.buyer)
        self.login(self.staff, staff=True)
        self.assertEqual(self.client.post(reverse("management:logout")).status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("management:index")).status_code, 302)

    def test_customer_logout_preserves_staff_session(self):
        self.login(self.buyer)
        self.login(self.staff, staff=True)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("management:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_staff_session_cannot_be_replayed_as_customer(self):
        self.login(self.staff, staff=True)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies["management_sessionid"].value
        for name, args, method in [("dashboard", [], "get"), ("account", [], "post"),
                                   ("order_confirm", [], "post"), ("pay_now", [1], "post"),
                                   ("vps_power", [1, "start"], "post"),
                                   ("windows_credentials", [1], "post")]:
            with self.subTest(name=name):
                response = getattr(self.client, method)(reverse(name, args=args))
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Customer.objects.filter(user=self.staff).exists())

    def test_customer_session_cannot_be_replayed_as_management(self):
        self.login(self.buyer)
        self.client.cookies["management_sessionid"] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(self.client.get(reverse("management:index")).status_code, 302)

    def test_csrf_cookies_and_validation_are_separate(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("login"))
        customer_csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        client.get(reverse("management:login"))
        staff_csrf = client.cookies["management_csrftoken"].value
        self.assertNotEqual(customer_csrf, staff_csrf)
        response = client.post(reverse("management:login"), {
            "username": self.staff.username, "password": self.password,
            "csrfmiddlewaretoken": customer_csrf,
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.post(reverse("management:login"), {
            "username": self.staff.username, "password": self.password,
            "csrfmiddlewaretoken": staff_csrf,
        }).status_code, 302)
        self.assertEqual(client.cookies[settings.CSRF_COOKIE_NAME].value, customer_csrf)

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                       SESSION_COOKIE_SAMESITE="Strict", CSRF_COOKIE_SECURE=True)
    def test_staff_cookie_attributes_preserve_security_settings(self):
        response = self.login(self.staff, staff=True)
        cookie = response.cookies["management_sessionid"]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertTrue(response.cookies["management_csrftoken"]["secure"])

    def test_customer_registration_cannot_create_staff(self):
        response = self.client.post(reverse("register"), {"username": "newbuyer",
            "password1": self.password, "password2": self.password, "full_name": "New Buyer",
            "email": "new@example.invalid", "is_staff": "on", "is_superuser": "on"})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newbuyer")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(Customer.objects.filter(user=user).exists())

    def test_existing_staff_customer_records_are_preserved(self):
        self.buyer.is_staff = True
        self.buyer.save()
        self.assertTrue(Customer.objects.filter(user=self.buyer).exists())
        plan = VPSPlan.objects.create(name="Legacy", cpu=2, ram=4, storage=64, monthly_price=299, yearly_price=2990)
        order = Order.objects.create(customer=self.buyer.customer_profile, plan=plan, amount=299, billing_cycle="MONTHLY")
        force_staff_login(self.client, self.root)
        self.assertContains(self.client.get(reverse("management:portal_order_change", args=[order.pk])), "Legacy")
        self.assertEqual(Customer.objects.filter(user=self.buyer).count(), 1)
        self.assertEqual(self.client.get(reverse("management:portal_customer_changelist")).context["cl"].result_count, 0)
        self.assertContains(self.client.get(reverse("management:portal_customer_change", args=[self.buyer.customer_profile.pk])),
                            "Historical staff-linked profile")
        cards = self.client.get(reverse("management:index")).context["cards"]
        self.assertEqual(next(card["count"] for card in cards if card["label"] == "Customers"), 0)

    def test_superuser_sees_staff_accounts_and_add_link(self):
        force_staff_login(self.client, self.root)
        self.assertContains(self.client.get(reverse("management:index")), "Staff accounts")
        response = self.client.get(self.staff_url())
        self.assertContains(response, self.staff.username)
        self.assertNotContains(response, ">buyer<")
        self.assertEqual(self.client.get(self.staff_url("add")).status_code, 200)

    def test_ordinary_staff_cannot_manage_staff_even_with_auth_permissions(self):
        self.staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="auth"))
        force_staff_login(self.client, self.staff)
        self.assertNotContains(self.client.get(reverse("management:index")), "Staff accounts")
        for action, pk in [("changelist", None), ("add", None), ("change", self.root.pk)]:
            with self.subTest(action=action):
                self.assertEqual(self.client.get(self.staff_url(action, pk)).status_code, 403)
                self.assertEqual(self.client.post(self.staff_url(action, pk), {}).status_code, 403)

    def test_create_staff_is_audited_and_skips_customer_profile(self):
        force_staff_login(self.client, self.root)
        response = self.client.post(self.staff_url("add"), {
            "username": "newoperator", "first_name": "New", "last_name": "Operator",
            "email": "staff@example.invalid", "password1": self.password, "password2": self.password,
            "is_superuser": "on", "is_staff": "", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        staff = User.objects.get(username="newoperator")
        self.assertTrue(staff.is_staff)
        self.assertFalse(staff.is_superuser)
        self.assertTrue(staff.check_password(self.password))
        self.assertFalse(Customer.objects.filter(user=staff).exists())
        self.assertTrue(LogEntry.objects.filter(user=self.root, object_id=str(staff.pk)).exists())

    def test_customer_cannot_be_edited_via_staff_account_urls(self):
        force_staff_login(self.client, self.root)
        self.assertEqual(self.client.get(self.staff_url("change", self.buyer.pk)).status_code, 302)
        self.assertEqual(self.client.post(self.staff_url("change", self.buyer.pk), {"is_staff": "on"}).status_code, 302)
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_staff)

    def test_superuser_is_readonly_on_staff_page(self):
        force_staff_login(self.client, self.root)
        self.assertEqual(self.client.get(self.staff_url("change", self.root.pk)).status_code, 200)
        self.assertEqual(self.client.post(self.staff_url("change", self.root.pk), {"is_active": ""}).status_code, 403)
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)

    def test_staff_permissions_and_deactivation(self):
        force_staff_login(self.client, self.root)
        permission = Permission.objects.get(content_type__app_label="portal", codename="view_order")
        response = self.client.post(self.staff_url("change", self.staff.pk), {
            "first_name": "Operator", "last_name": "", "email": "", "is_active": "on",
            "user_permissions": [permission.pk], "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        operator = Client()
        self.login(self.staff, staff=True, client=operator)
        self.assertEqual(operator.get(reverse("management:portal_order_changelist")).status_code, 200)
        self.assertEqual(operator.get(reverse("management:portal_payment_changelist")).status_code, 403)
        self.assertEqual(self.client.post(self.staff_url("change", self.staff.pk), {
            "first_name": "Operator", "last_name": "", "email": "", "user_permissions": [permission.pk],
        }).status_code, 302)
        self.assertEqual(operator.get(reverse("management:index")).status_code, 302)

    def test_staff_delete_is_disabled(self):
        force_staff_login(self.client, self.root)
        self.assertEqual(self.client.post(self.staff_url("delete", self.staff.pk), {"post": "yes"}).status_code, 403)

    def test_staff_messages_do_not_leak_to_customer_portal(self):
        self.login(self.buyer)
        self.login(self.root, staff=True)
        response = self.client.post(self.staff_url("add"), {"username": "message-test-staff",
            "password1": self.password, "password2": self.password, "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("management_messages", response.cookies)
        self.assertNotIn("messages", response.cookies)
        self.assertNotContains(self.client.get(reverse("dashboard")), "was added successfully")
        self.assertContains(self.client.get(reverse("management:index")), "was added successfully")
