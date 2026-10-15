"""Billing preservation, authorization, invoice identity and repeat-safety tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Invoice, Order, Payment, Subscription, VPSPlan, XenditCheckout
from .payments import record_verified_payment
from .provisioning import require_paid
from .renewals import generate_invoice, period_end, review
from .test_management import force_staff_login


def fixture():
    owner = User.objects.create_user('renewal-owner', is_staff=True, is_superuser=True)
    customer = User.objects.create_user('renewal-customer').customer_profile
    plan = VPSPlan.objects.create(name='Renewal plan', cpu=2, ram=2, storage=40,
                                  monthly_price=299, yearly_price=2990)
    order = Order.objects.create(customer=customer, plan=plan, billing_cycle='MONTHLY',
                                 amount=Decimal('249.00'), status='ACTIVE')
    now = timezone.now()
    invoice = Invoice.objects.create(order=order, invoice_number='INITIAL-RENEWAL-TEST',
        amount=order.amount, due_date=now, status='PAID', paid_at=now)
    Payment.objects.create(invoice=invoice, transaction_id='initial-paid', provider='XENDIT',
                           amount=order.amount, status='SUCCESS', paid_at=now)
    sub = Subscription.objects.create(order=order, customer=customer, start_date=now-timedelta(days=25),
        next_billing_date=now+timedelta(days=5), renewal_amount=order.amount,
        renewal_cycle='MONTHLY', renewal_currency='PHP')
    return owner, customer, order, invoice, sub


@override_settings(RENEWAL_INVOICING_ENABLED=True, RENEWAL_INVOICE_LEAD_DAYS=7)
class RenewalTests(TestCase):
    def setUp(self):
        self.owner, self.customer, self.order, self.initial, self.sub = fixture()

    def issue(self):
        return generate_invoice(self.sub.pk, actor=self.owner, expected_due=self.sub.next_billing_date)

    @patch('requests.Session.request', side_effect=AssertionError('No external calls allowed'))
    def test_repeated_generation_preserves_price_entitlement_and_purchase(self, network):
        before = (self.sub.start_date, self.sub.next_billing_date, self.sub.status)
        invoice, created = self.issue()
        repeated, second_created = self.issue()
        self.assertTrue(created)
        self.assertFalse(second_created)
        self.assertEqual(invoice.pk, repeated.pk)
        self.assertEqual(invoice.amount, Decimal('249.00'))
        self.assertNotEqual(invoice.amount, self.order.plan.monthly_price)
        self.assertEqual(invoice.due_date, self.sub.next_billing_date)
        self.assertEqual(invoice.period_start, self.sub.next_billing_date)
        self.assertGreater(invoice.period_end, invoice.period_start)
        self.assertEqual((invoice.purpose, invoice.currency, invoice.status), ('RENEWAL', 'PHP', 'PENDING'))
        self.sub.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.sub.start_date, self.sub.next_billing_date, self.sub.status), before)
        self.assertEqual(self.order.status, 'ACTIVE')
        self.assertEqual(self.order.invoice.pk, self.initial.pk)
        self.assertEqual(Invoice.objects.filter(purpose='RENEWAL').count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(XenditCheckout.objects.count(), 0)
        self.assertEqual(LogEntry.objects.filter(object_id=str(invoice.pk)).count(), 1)
        network.assert_not_called()

    def test_initial_payment_and_provisioning_ignore_renewal(self):
        renewal, _ = self.issue()
        # A pending renewal cannot obscure the original invoice or turn it unpaid.
        self.assertEqual(require_paid(self.order).pk, self.initial.pk)
        with patch('portal.payments.request_vps_provisioning') as provisioning:
            with self.captureOnCommitCallbacks(execute=True):
                payment = record_verified_payment(order_id=self.order.pk, provider='XENDIT',
                    transaction_id='initial-paid', amount=self.order.amount)
            self.assertEqual(payment.invoice_id, self.initial.pk)
        renewal.refresh_from_db()
        self.assertEqual(renewal.status, 'PENDING')
        Invoice.objects.filter(pk=self.initial.pk).update(status='PENDING')
        Invoice.objects.filter(pk=renewal.pk).update(status='PAID', paid_at=timezone.now())
        Payment.objects.create(invoice=renewal, provider='XENDIT', transaction_id='wrong-renewal-proof',
                               amount=renewal.amount, status='SUCCESS', paid_at=timezone.now())
        with self.assertRaises(ValidationError):
            require_paid(self.order)

    def test_generation_is_disabled_by_default_and_requires_active_owner(self):
        with override_settings(RENEWAL_INVOICING_ENABLED=False), self.assertRaises(ValidationError):
            self.issue()
        staff = User.objects.create_user('renewal-staff', is_staff=True)
        for actor in (staff, self.customer.user, None):
            with self.assertRaises(PermissionDenied):
                generate_invoice(self.sub.pk, actor=actor, expected_due=self.sub.next_billing_date)
        self.owner.is_active = False
        with self.assertRaises(PermissionDenied):
            self.issue()
        self.assertEqual(Invoice.objects.count(), 1)

    def test_overdue_future_cancelled_and_inconsistent_services_need_review(self):
        original_due = self.sub.next_billing_date
        for due in (timezone.now()-timedelta(days=1), timezone.now()+timedelta(days=20)):
            Subscription.objects.filter(pk=self.sub.pk).update(next_billing_date=due)
            with self.assertRaises(ValidationError):
                generate_invoice(self.sub.pk, actor=self.owner, expected_due=due)
        Subscription.objects.filter(pk=self.sub.pk).update(next_billing_date=original_due)
        for change in ({'status': 'CANCELLED'}, {'status': 'EXPIRED'}, {'renewal_amount': None},
                       {'renewal_amount': 0}, {'renewal_cycle': ''}, {'renewal_currency': 'USD'}):
            with transaction.atomic():
                Subscription.objects.filter(pk=self.sub.pk).update(**change)
                with self.assertRaises(ValidationError):
                    self.issue()
                transaction.set_rollback(True)
        Payment.objects.all().delete()
        with self.assertRaises(ValidationError):
            self.issue()
        self.assertEqual(Invoice.objects.count(), 1)

    def test_stale_review_and_invalid_ownership_are_rejected(self):
        Subscription.objects.filter(pk=self.sub.pk).update(next_billing_date=timezone.now()+timedelta(days=4))
        with self.assertRaisesMessage(ValidationError, 'billing date changed'):
            self.issue()
        other = User.objects.create_user('other-owner').customer_profile
        self.sub.customer = other
        self.sub.save(update_fields=['customer'])
        self.assertFalse(review(self.sub)['eligible'])

    def test_database_rejects_duplicate_initial_or_renewal_period_and_invalid_shape(self):
        renewal, _ = self.issue()
        duplicates = [dict(order=self.order, amount=1, due_date=timezone.now()),
                      dict(order=self.order, amount=1, due_date=timezone.now(), purpose='RENEWAL',
                           subscription=self.sub, period_start=renewal.period_start, period_end=renewal.period_end),
                      dict(order=self.order, amount=1, due_date=timezone.now(), purpose='RENEWAL')]
        for i, values in enumerate(duplicates):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Invoice.objects.create(invoice_number=f'invalid-{i}', **values)

    def test_month_end_leap_year_and_yearly_anchor(self):
        self.sub.start_date = datetime(2027, 1, 31, 12, tzinfo=dt_timezone.utc)
        self.sub.next_billing_date = datetime(2027, 2, 28, 12, tzinfo=dt_timezone.utc)
        self.assertEqual(period_end(self.sub), datetime(2027, 3, 31, 12, tzinfo=dt_timezone.utc))
        self.sub.start_date = datetime(2028, 2, 29, 12, tzinfo=dt_timezone.utc)
        self.sub.next_billing_date = datetime(2031, 2, 28, 12, tzinfo=dt_timezone.utc)
        self.sub.renewal_cycle = 'YEARLY'
        self.assertEqual(period_end(self.sub), datetime(2032, 2, 29, 12, tzinfo=dt_timezone.utc))

    def test_customer_invoice_identity_and_cross_customer_access(self):
        renewal, _ = self.issue()
        self.client.force_login(self.customer.user)
        response = self.client.get(reverse('invoice_detail', args=[renewal.pk]))
        self.assertContains(response, renewal.invoice_number)
        self.assertNotContains(response, reverse('pay_now', args=[self.order.pk]))
        self.assertNotContains(response, 'provisioning-status')
        self.assertContains(self.client.get(reverse('invoice', args=[self.order.pk])), self.initial.invoice_number)
        self.assertContains(self.client.get(reverse('invoices')), reverse('invoice_detail', args=[renewal.pk]))
        for name, args in [('my_vps', []), ('vps_detail', [self.order.pk]), ('dashboard', []),
                           ('orders', []), ('order_detail', [self.order.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        other = User.objects.create_user('invoice-other-customer')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('invoice_detail', args=[renewal.pk])).status_code, 404)

    def test_staff_permissions_readonly_get_and_post_review(self):
        url = reverse('management:renewals')
        staff = User.objects.create_user('renewal-viewer', is_staff=True)
        force_staff_login(self.client, staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=['view_subscription', 'view_invoice'],
                                                              content_type__app_label='portal'))
        response = self.client.get(url)
        self.assertContains(response, 'VPS renewals')
        self.assertNotContains(response, 'Review invoice</a>')
        issue_url = reverse('management:renewal_invoice', args=[self.sub.pk])
        self.assertEqual(self.client.post(issue_url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 405)
        force_staff_login(self.client, self.owner)
        response = self.client.get(issue_url)
        self.assertEqual(Invoice.objects.count(), 1)
        token = response.context['review_token']
        self.client.post(issue_url, {'review_token': token})
        self.client.post(issue_url, {'review_token': token})
        self.assertEqual(Invoice.objects.filter(purpose='RENEWAL').count(), 1)
        self.assertEqual(self.client.get(url+'?status=unpaid').context['page'].paginator.count, 1)

    def test_bad_review_token_and_csrf_cannot_issue(self):
        force_staff_login(self.client, self.owner)
        url = reverse('management:renewal_invoice', args=[self.sub.pk])
        self.client.post(url, {'review_token': 'tampered'})
        wrong = signing.dumps({'subscription': self.sub.pk+100, 'due': self.sub.next_billing_date.isoformat()},
                              salt='renewal-review')
        self.client.post(url, {'review_token': wrong})
        self.client.handler.enforce_csrf_checks = True
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_changed_agreement_invalidates_review_and_misaligned_dates_need_review(self):
        force_staff_login(self.client, self.owner)
        url = reverse('management:renewal_invoice', args=[self.sub.pk])
        token = self.client.get(url).context['review_token']
        Subscription.objects.filter(pk=self.sub.pk).update(renewal_amount='1.00')
        self.client.post(url, {'review_token': token})
        self.assertEqual(Invoice.objects.count(), 1)
        self.sub.next_billing_date += timedelta(days=1)
        self.assertIn('anniversary', review(self.sub)['reason'])

    def test_dry_run_and_explicit_operator_apply(self):
        output = StringIO()
        call_command('generate_renewal_invoices', dry_run=True, stdout=output)
        self.assertIn('Dry run', output.getvalue())
        self.assertEqual(Invoice.objects.count(), 1)
        with self.assertRaises(CommandError):
            call_command('generate_renewal_invoices', apply=True)
        call_command('generate_renewal_invoices', apply=True, ids=[self.sub.pk],
                     actor=self.owner.username, stdout=StringIO())
        self.assertEqual(Invoice.objects.filter(purpose='RENEWAL').count(), 1)


@override_settings(RENEWAL_INVOICING_ENABLED=True, RENEWAL_INVOICE_LEAD_DAYS=7)
class RenewalConcurrencyTests(TransactionTestCase):
    def test_two_postgresql_workers_create_one_invoice_and_audit_entry(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Real locking/concurrency requires PostgreSQL.')
        owner, customer, order, initial, sub = fixture()
        def worker(_):
            close_old_connections()
            try:
                actor = User.objects.get(pk=owner.pk)
                invoice, created = generate_invoice(sub.pk, actor=actor, expected_due=sub.next_billing_date)
                return invoice.pk, created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(Invoice.objects.filter(purpose='RENEWAL').count(), 1)
        self.assertEqual(LogEntry.objects.count(), 1)
