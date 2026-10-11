from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Invoice, Order, Payment, Subscription, VPSPlan
from .provisioning_api import ProvisioningResult


class ManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("operator", is_staff=True)
        cls.customer = User.objects.create_user("customer")
        cls.plan = VPSPlan.objects.create(name="Compute", cpu=2, ram=4, storage=64,
                                          monthly_price=299, yearly_price=2990)
        cls.order = Order.objects.create(customer=cls.customer.customer_profile, plan=cls.plan,
            billing_cycle="MONTHLY", amount=299, status="PROVISIONING", provisioning_vmid="1020",
            provisioning_payload={"secret": "PRIVATE-PAYLOAD"}, ssh_public_key="PRIVATE-KEY-FIELD")
        cls.invoice = Invoice.objects.create(order=cls.order, invoice_number="INV-1", amount=299,
                                             due_date=timezone.now())
        cls.payment = Payment.objects.create(invoice=cls.invoice, provider="XENDIT", transaction_id="tx1",
                                             amount=299, raw_response={"secret": "PRIVATE-RAW-RESPONSE"})
        cls.subscription = Subscription.objects.create(customer=cls.customer.customer_profile,
            order=cls.order, start_date=timezone.now(), next_billing_date=timezone.now())

    def grant(self, *codes):
        self.staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="portal", codename__in=codes))
        self.client.force_login(self.staff)

    def url(self, model, action="changelist", pk=None):
        return reverse(f"management:portal_{model}_{action}", args=[pk] if pk else [])

    def protected_urls(self):
        return [reverse("management:index"), reverse("management:services"),
                self.url("order", "sync", self.order.pk)] + [self.url(name) for name in
                ("customer", "vpsplan", "order", "invoice", "payment", "subscription")]

    def test_anonymous_and_nonstaff_cannot_access_management(self):
        for user in (None, self.customer):
            if user:
                self.client.force_login(user)
            for url in self.protected_urls():
                with self.subTest(user=user, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn("/management/login/", response.url)

    def test_inactive_staff_cannot_access(self):
        self.staff.is_active = False
        self.staff.save()
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("management:index")).status_code, 302)

    def test_legacy_admin_rejects_staff_bypass_and_preserves_superuser_access(self):
        self.grant("view_order", "change_order")
        url = reverse("admin:portal_order_change", args=[self.order.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url, {"status": "PAID"}).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "PROVISIONING")
        self.staff.is_superuser = True
        self.staff.save()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 200)

    def test_legacy_login_rejects_ordinary_staff(self):
        from .management_admin import LegacyAdminAuthenticationForm
        with self.assertRaises(ValidationError):
            LegacyAdminAuthenticationForm().confirm_login_allowed(self.staff)

    def test_services_pagination_preserves_filtered_records(self):
        self.grant("view_order")
        Order.objects.bulk_create([Order(customer=self.customer.customer_profile, plan=self.plan,
            billing_cycle="MONTHLY", amount=299, status="FAILED") for _ in range(31)])
        response = self.client.get(reverse("management:services"), {"status": "FAILED", "page": 2})
        self.assertEqual(response.context["page"].paginator.count, 31)
        self.assertEqual(len(response.context["page"]), 1)

    def test_staff_navigation_is_not_shown_to_customers(self):
        self.client.force_login(self.customer)
        self.assertNotContains(self.client.get(reverse("dashboard")), 'href="/management/"')
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("dashboard")), 'href="/management/"')

    def test_staff_without_model_permissions_sees_no_records(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("management:index"))
        self.assertContains(response, "No record permissions assigned")
        for url in self.protected_urls()[1:]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_model_permissions_are_separate(self):
        self.grant("view_invoice")
        self.assertEqual(self.client.get(self.url("invoice")).status_code, 200)
        self.assertEqual(self.client.get(self.url("payment")).status_code, 403)
        response = self.client.get(reverse("management:index"))
        self.assertEqual([c["label"] for c in response.context["cards"]], ["Invoices"])

    def test_all_sections_and_record_pages_render(self):
        records = {"customer": self.customer.customer_profile, "vpsplan": self.plan,
                   "order": self.order, "invoice": self.invoice, "payment": self.payment,
                   "subscription": self.subscription}
        self.grant(*(f"view_{name}" for name in records))
        for name, record in records.items():
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 200)
                self.assertEqual(self.client.get(self.url(name, "change", record.pk)).status_code, 200)

    def test_readonly_workflows_reject_forged_edits_even_with_change_permission(self):
        records = {"order": self.order, "invoice": self.invoice, "payment": self.payment,
                   "subscription": self.subscription}
        self.grant(*(f"{perm}_{name}" for name in records for perm in ("view", "change", "add", "delete")))
        for name, record in records.items():
            with self.subTest(name=name):
                previous = record.status
                self.assertEqual(self.client.post(self.url(name, "change", record.pk), {"status": "PAID"}).status_code, 403)
                self.assertEqual(self.client.post(self.url(name, "add"), {}).status_code, 403)
                self.assertEqual(self.client.post(self.url(name, "delete", record.pk), {"post": "yes"}).status_code, 403)
                record.refresh_from_db()
                self.assertEqual(record.status, previous)

    def test_sensitive_raw_fields_are_not_rendered(self):
        self.grant("view_order", "view_payment")
        order = self.client.get(self.url("order", "change", self.order.pk))
        self.assertNotContains(order, "PRIVATE-PAYLOAD")
        self.assertNotContains(order, "PRIVATE-KEY-FIELD")
        self.assertNotContains(self.client.get(self.url("payment", "change", self.payment.pk)), "PRIVATE-RAW-RESPONSE")

    @patch("portal.management_admin.provisioning.get_vps_provisioning_status")
    def test_services_filters_and_gets_never_contact_provisioner(self, sync):
        self.grant("view_order")
        url = reverse("management:services")
        self.assertContains(self.client.get(url), "1020")
        self.assertContains(self.client.get(url, {"q": "1020"}), "1020")
        self.assertContains(self.client.get(url, {"q": "missing"}), "No VPS services")
        self.assertContains(self.client.get(url, {"status": "ACTIVE"}), "No VPS services")
        self.assertEqual(self.client.get(url, {"q": "9" * 200}).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 405)
        sync.assert_not_called()

    @patch("portal.management_admin.provisioning.get_vps_provisioning_status")
    def test_sync_requires_change_permission(self, sync):
        self.grant("view_order")
        url = self.url("order", "sync", self.order.pk)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        sync.assert_not_called()

    @patch("portal.management_admin.provisioning.get_vps_provisioning_status")
    def test_sync_confirmation_and_post_reuse_workflow_and_log_actor(self, sync):
        self.grant("view_order", "change_order")
        sync.return_value = self.order
        url = self.url("order", "sync", self.order.pk)
        self.assertContains(self.client.get(url), "Reconcile status")
        sync.assert_not_called()
        self.assertEqual(self.client.post(url).status_code, 302)
        sync.assert_called_once_with(self.order)
        self.assertTrue(LogEntry.objects.filter(user=self.staff, object_id=str(self.order.pk)).exists())
        overview = self.client.get(reverse("management:index"))
        self.assertContains(overview, self.url("order", "change", self.order.pk))
        self.assertNotContains(overview, 'href="/admin/')
        self.staff.user_permissions.clear()
        self.assertEqual(self.client.get(reverse("management:index")).context["recent_actions"], [])

    @patch("portal.management_admin.provisioning.get_vps_provisioning_status")
    def test_sync_requires_csrf_and_rejects_other_methods(self, sync):
        self.grant("view_order", "change_order")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        url = self.url("order", "sync", self.order.pk)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(self.client.put(url).status_code, 405)
        sync.assert_not_called()

    @patch("portal.management_admin.provisioning.get_vps_provisioning_status", side_effect=ValidationError("Payment required."))
    def test_sync_validation_is_shown_without_mutation(self, sync):
        self.grant("view_order", "change_order")
        response = self.client.post(self.url("order", "sync", self.order.pk), follow=True)
        self.assertContains(response, "Payment required.")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "PROVISIONING")

    def test_customer_edit_cannot_reassign_user(self):
        self.grant("view_customer", "change_customer")
        profile = self.customer.customer_profile
        response = self.client.post(self.url("customer", "change", profile.pk), {
            "full_name": "Updated name", "phone": "123", "company": "ICT", "user": self.staff.pk,
        })
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.full_name, "Updated name")
        self.assertEqual(profile.user_id, self.customer.pk)
        self.assertTrue(LogEntry.objects.filter(user=self.staff, object_id=str(profile.pk)).exists())

    def test_view_only_customer_cannot_edit(self):
        self.grant("view_customer")
        self.assertEqual(self.client.post(self.url("customer", "change", self.customer.customer_profile.pk),
                                         {"full_name": "Forged"}).status_code, 403)

    def test_plan_with_orders_keeps_resource_contract(self):
        self.grant("view_vpsplan", "change_vpsplan")
        response = self.client.post(self.url("vpsplan", "change", self.plan.pk), {
            "name": "Forged", "description": "Updated", "cpu": 100, "ram": 100, "storage": 100,
            "monthly_price": "399", "yearly_price": "3990", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.plan.refresh_from_db()
        self.assertEqual((self.plan.name, self.plan.cpu, self.plan.ram, self.plan.storage), ("Compute", 2, 4, 64))
        self.assertEqual(self.plan.monthly_price, 399)

    def test_new_plan_validation(self):
        self.grant("view_vpsplan", "add_vpsplan")
        data = {"name": "New", "cpu": 0, "ram": 4, "storage": 64,
                "monthly_price": -1, "yearly_price": 2990, "is_active": "on"}
        response = self.client.post(self.url("vpsplan", "add"), data)
        self.assertContains(response, "Resources must be at least 1.")
        self.assertContains(response, "Price cannot be negative.")
        self.assertFalse(VPSPlan.objects.filter(name="New").exists())
        data.update(cpu=2, monthly_price=299)
        self.assertEqual(self.client.post(self.url("vpsplan", "add"), data).status_code, 302)
        self.assertTrue(VPSPlan.objects.filter(name="New").exists())


class ManagementWorkflowTests(TransactionTestCase):
    def test_sync_real_workflow_refuses_unpaid_order(self):
        staff = User.objects.create_user("operator", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="portal",
                                  codename__in=["view_order", "change_order"]))
        plan = VPSPlan.objects.create(name="Compute", cpu=2, ram=4, storage=64,
                                     monthly_price=299, yearly_price=2990)
        order = Order.objects.create(customer=staff.customer_profile, plan=plan,
                                     billing_cycle="MONTHLY", amount=299)
        self.client.force_login(staff)
        with patch("portal.provisioning.api_request") as api:
            response = self.client.post(reverse("management:portal_order_sync", args=[order.pk]), follow=True)
        self.assertContains(response, "A verified server-side payment is required.")
        api.assert_not_called()

    def test_paid_reconciliation_uses_get_and_reuses_subscription(self):
        staff = User.objects.create_user("operator", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="portal",
                                  codename__in=["view_order", "change_order"]))
        plan = VPSPlan.objects.create(name="Compute", cpu=2, ram=4, storage=64,
                                     monthly_price=299, yearly_price=2990)
        order = Order.objects.create(customer=staff.customer_profile, plan=plan,
            billing_cycle="MONTHLY", amount=299, status="PROVISIONING", provisioning_payload={"order_id": 1})
        invoice = Invoice.objects.create(order=order, invoice_number="PAID-1", amount=299,
            status="PAID", due_date=timezone.now(), paid_at=timezone.now())
        Payment.objects.create(invoice=invoice, provider="VERIFIED_FIXTURE", transaction_id="paid1",
                               amount=299, status="SUCCESS", paid_at=timezone.now())
        self.client.force_login(staff)
        url = reverse("management:portal_order_sync", args=[order.pk])
        result = ProvisioningResult(status="ACTIVE", vps_id="20", vmid="1020", progress=100,
                                    ip_address="10.60.0.20", ssh_host="ssh.example.invalid", ssh_port=22020)
        with patch("portal.provisioning.api_request", return_value=result) as api:
            self.assertEqual(self.client.post(url).status_code, 302)
            api.assert_called_once_with("GET", order.pk, payload=None)
            self.assertEqual(self.client.post(url).status_code, 302)
            self.assertEqual(api.call_count, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, "ACTIVE")
        self.assertEqual(Subscription.objects.filter(order=order).count(), 1)
