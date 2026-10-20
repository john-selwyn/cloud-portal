import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import BillingCycleForm
from .models import Invoice, Order, VPSPlan
from .services import confirm_order


KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEjYzQzM0MTA0Y2QyNDhlMjQ5MTk2ZDA2ZDBlMTA1YzQ2ZTU test@example"
SERVER = "Ubuntu Server 26.04"


@override_settings(UBUNTU_SERVER_ORDERING_ENABLED=True, WINDOWS_ORDERING_ENABLED=False)
class UbuntuServerCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("server-buyer")
        self.plan = VPSPlan.objects.create(name="Server", cpu=2, ram=4, storage=50,
                                          monthly_price="299.00", yearly_price="2990.00")
        self.client.force_login(self.user)

    def confirm(self, token=None):
        return confirm_order(customer=self.user.customer_profile, plan_id=self.plan.pk,
                             cycle="MONTHLY", checkout_token=token or uuid.uuid4(),
                             reviewed_amount="299.00", operating_system=SERVER,
                             ssh_username="vpsuser", ssh_public_key=KEY)

    def test_server_uses_linux_key_validation_and_independent_switch(self):
        form = BillingCycleForm({"operating_system": SERVER, "billing_cycle": "MONTHLY"}, plan=self.plan)
        self.assertFalse(form.is_valid())
        self.assertIn("ssh_public_key", form.errors)
        choices = dict(form.fields["operating_system"].choices)
        self.assertIn(SERVER, choices)
        self.assertNotIn("Windows 11", choices)
        self.assertEqual(choices["Ubuntu 26.04"], "Ubuntu Desktop 26.04 LTS")

    @override_settings(UBUNTU_SERVER_ORDERING_ENABLED=False, WINDOWS_ORDERING_ENABLED=True)
    def test_disabled_server_is_hidden_and_cannot_create_order(self):
        form = BillingCycleForm({"operating_system": SERVER, "billing_cycle": "MONTHLY",
                                 "ssh_public_key": KEY}, plan=self.plan)
        self.assertFalse(form.is_valid())
        choices = dict(form.fields["operating_system"].choices)
        self.assertNotIn(SERVER, choices)
        self.assertIn("Windows 11", choices)
        with self.assertRaises(ValidationError):
            self.confirm()
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_review_confirmation_keeps_server_and_ssh_configuration(self):
        review = self.client.post(reverse("select_plan", args=[self.plan.pk]),
                                  {"operating_system": SERVER, "billing_cycle": "MONTHLY",
                                   "ssh_public_key": KEY})
        self.assertEqual(review.status_code, 200)
        token = review.context["checkout_token"]
        response = self.client.post(reverse("order_confirm"),
                                    {"checkout_token": token, "operating_system": "Ubuntu 26.04"})
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.operating_system, SERVER)
        self.assertEqual((order.ssh_username, order.ssh_public_key), ("vpsuser", KEY))
        self.assertEqual(Invoice.objects.count(), 1)

    def test_disabling_new_orders_does_not_break_existing_token_retry(self):
        token = uuid.uuid4()
        original = self.confirm(token)
        with override_settings(UBUNTU_SERVER_ORDERING_ENABLED=False):
            retry = self.confirm(token)
        self.assertEqual(retry.pk, original.pk)
        self.assertEqual(Invoice.objects.count(), 1)
