"""Presentation must retain permission boundaries and the separate admin surface."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .test_management import force_staff_login


class ManagementPresentationTests(TestCase):
    def test_limited_staff_navigation_exposes_only_allowed_record_areas(self):
        staff = User.objects.create_user("invoice-reader", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(
            content_type__app_label="portal", codename="view_invoice"))
        force_staff_login(self.client, staff)
        response = self.client.get(reverse("management:index"))
        self.assertContains(response, "management.css")
        self.assertContains(response, 'aria-label="Management"')
        self.assertContains(response, reverse("management:portal_invoice_changelist"))
        for name in ("portal_order_changelist", "portal_payment_changelist",
                     "portal_customer_changelist", "auth_user_changelist", "services"):
            self.assertNotContains(response, 'href="' + reverse("management:" + name) + '"')

    def test_staff_logout_remains_post_and_uses_management_session(self):
        staff = User.objects.create_user("operator-ui", is_staff=True)
        force_staff_login(self.client, staff)
        response = self.client.get(reverse("management:index"))
        self.assertContains(response, 'method="post" action="' + reverse("management:logout") + '"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, 'action="/accounts/logout/"')

    def test_login_is_themed_but_does_not_expose_workspace_navigation(self):
        response = self.client.get(reverse("management:login"))
        self.assertContains(response, "management.css")
        self.assertNotContains(response, 'aria-label="Management"')
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_customer_and_legacy_admin_do_not_load_management_theme(self):
        customer = User.objects.create_user("customer-ui")
        self.client.force_login(customer)
        self.assertNotContains(self.client.get(reverse("dashboard")), "management.css")
        owner = User.objects.create_superuser("owner-ui", "owner@example.invalid", "test-only-password")
        force_staff_login(self.client, owner)
        self.assertNotContains(self.client.get(reverse("admin:index")), "management.css")
        self.assertContains(self.client.get(reverse("management:index")), reverse("management:auth_user_changelist"))
