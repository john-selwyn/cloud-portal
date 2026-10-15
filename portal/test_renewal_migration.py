"""Rehearse the real schema transition against representative pre-renewal rows."""
from datetime import timedelta

from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RenewalMigrationTests(TransactionTestCase):
    old = [('portal', '0011_order_rdp_host_order_rdp_port')]
    new = [('portal', '0012_renewal_invoice_foundation')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old)
        self.apps = executor.loader.project_state(self.old).apps
        self.now = timezone.now()
        User = self.apps.get_model('auth', 'User')
        Customer = self.apps.get_model('portal', 'Customer')
        Plan = self.apps.get_model('portal', 'VPSPlan')
        Order = self.apps.get_model('portal', 'Order')
        Invoice = self.apps.get_model('portal', 'Invoice')
        user = User.objects.create(username='historic-renewal-user')
        customer = Customer.objects.create(user=user, full_name='Historic customer')
        plan = Plan.objects.create(name='Historical plan', cpu=2, ram=2, storage=40,
                                  monthly_price=999, yearly_price=9990)
        self.order = Order.objects.create(customer=customer, plan=plan, amount='249.00',
                                          billing_cycle='MONTHLY', status='ACTIVE')
        self.invoice = Invoice.objects.create(order=self.order, invoice_number='INV-HISTORIC', amount='249.00',
            due_date=self.now, status='PAID', paid_at=self.now)
        self.payment = self.apps.get_model('portal', 'Payment').objects.create(invoice=self.invoice,
            provider='XENDIT', transaction_id='historic-payment', amount='249.00', status='SUCCESS', paid_at=self.now)
        self.checkout = self.apps.get_model('portal', 'XenditCheckout').objects.create(order=self.order,
            reference_id='historic-session-reference', payment_session_id='historic-session',
            status='COMPLETED', amount='249.00', verified_payment_id='historic-payment')
        self.sub = self.apps.get_model('portal', 'Subscription').objects.create(order=self.order,
            customer=customer, start_date=self.now-timedelta(days=25), next_billing_date=self.now+timedelta(days=5))

    def tearDown(self):
        # Restore the latest schema for subsequent tests, including a failed backfill rehearsal.
        self.apps.get_model('portal', 'Invoice').objects.filter(pk=self.invoice.pk).update(amount='249.00')
        MigrationExecutor(connection).migrate(self.new)
        super().tearDown()

    def migrate(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.new)
        return executor.loader.project_state(self.new).apps

    def test_original_ids_amounts_payments_sessions_and_dates_are_preserved(self):
        apps = self.migrate()
        invoice = apps.get_model('portal', 'Invoice').objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.invoice_number, str(invoice.amount), invoice.order_id, invoice.status),
                         ('INV-HISTORIC', '249.00', self.order.pk, 'PAID'))
        self.assertEqual(invoice.purpose, 'INITIAL')
        self.assertIsNone(invoice.subscription_id)
        self.assertEqual(invoice.paid_at, self.now)
        sub = apps.get_model('portal', 'Subscription').objects.get(pk=self.sub.pk)
        self.assertEqual(str(sub.renewal_amount), '249.00')
        self.assertEqual(sub.renewal_cycle, 'MONTHLY')
        self.assertEqual(sub.next_billing_date, self.sub.next_billing_date)
        self.assertEqual(sub.start_date, self.sub.start_date)
        payment = apps.get_model('portal', 'Payment').objects.get(pk=self.payment.pk)
        checkout = apps.get_model('portal', 'XenditCheckout').objects.get(pk=self.checkout.pk)
        self.assertEqual(payment.invoice_id, invoice.pk)
        self.assertEqual(payment.transaction_id, 'historic-payment')
        self.assertEqual((checkout.order_id, checkout.reference_id, checkout.payment_session_id),
                         (self.order.pk, 'historic-session-reference', 'historic-session'))
        self.assertEqual(apps.get_model('portal', 'Invoice').objects.count(), 1)

    def test_ambiguous_agreement_stops_backfill_instead_of_guessing(self):
        self.apps.get_model('portal', 'Invoice').objects.filter(pk=self.invoice.pk).update(amount='1.00')
        with self.assertRaisesMessage(RuntimeError, 'original billing agreement needs review'):
            self.migrate()

    def test_reverse_is_blocked_before_discarding_renewal_history(self):
        apps = self.migrate()
        Invoice = apps.get_model('portal', 'Invoice')
        Invoice.objects.create(order_id=self.order.pk, subscription_id=self.sub.pk, purpose='RENEWAL',
            invoice_number='REN-MIGRATION', amount='249.00', due_date=self.sub.next_billing_date,
            period_start=self.sub.next_billing_date, period_end=self.sub.next_billing_date+timedelta(days=31))
        with self.assertRaises(IrreversibleError):
            MigrationExecutor(connection).migrate(self.old)
        self.assertEqual(Invoice.objects.filter(purpose='RENEWAL').count(), 1)
