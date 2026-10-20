"""Rehearse the additive migration using representative old-schema records."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class AccountMigrationTests(TransactionTestCase):
    def test_existing_accounts_and_financial_records_are_preserved(self):
        before = [("portal", "0011_order_rdp_host_order_rdp_port")]
        after = [("portal", "0012_customer_accounts")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            user = apps.get_model("auth", "User").objects.create(
                username="legacy-buyer", email="Legacy@Example.invalid", password="unusable-test-hash",
                is_active=True, is_staff=False, is_superuser=False)
            customer = apps.get_model("portal", "Customer").objects.create(user_id=user.pk, full_name="Legacy Buyer")
            plan = apps.get_model("portal", "VPSPlan").objects.create(
                name="Legacy Plan", cpu=2, ram=4, storage=64, monthly_price="299.00", yearly_price="2990.00")
            order = apps.get_model("portal", "Order").objects.create(
                customer_id=customer.pk, plan_id=plan.pk, billing_cycle="MONTHLY", amount="299.00", status="ACTIVE")
            invoice = apps.get_model("portal", "Invoice").objects.create(
                order_id=order.pk, invoice_number="LEGACY-TEST-1", amount="299.00", status="PAID", due_date=timezone.now())
            apps.get_model("portal", "Payment").objects.create(
                invoice_id=invoice.pk, provider="TEST", transaction_id="legacy-test-1", amount="299.00", status="SUCCESS")
            apps.get_model("portal", "Subscription").objects.create(
                customer_id=customer.pk, order_id=order.pk, start_date=timezone.now(), next_billing_date=timezone.now())
            names = ["Customer", "Order", "Invoice", "Payment", "Subscription"]
            snapshot = {name: list(apps.get_model("portal", name).objects.values().order_by("pk")) for name in names}
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new_apps = executor.loader.project_state(after).apps
            for name in names:
                rows = list(new_apps.get_model("portal", name).objects.values().order_by("pk"))
                if name == "Customer":
                    self.assertFalse(rows[0].pop("email_verification_required"))
                self.assertEqual(rows, snapshot[name], name)
            updated_user = new_apps.get_model("auth", "User").objects.get(pk=user.pk)
            self.assertEqual(updated_user.email, "Legacy@Example.invalid")
            self.assertEqual(updated_user.password, "unusable-test-hash")
            self.assertTrue(updated_user.is_active)
            self.assertEqual(new_apps.get_model("portal", "CustomerEmail").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(after)
