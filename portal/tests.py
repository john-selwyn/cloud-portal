from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Customer, Invoice, Order, Payment, Subscription, VPSPlan


TEST_SSH_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEjYzQzM0MTA0Y2QyNDhlMjQ5MTk2ZDA2ZDBlMTA1YzQ2ZTU test@example"


class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('alice', password='Test-Password-9821')
        cls.other = User.objects.create_user('bob', password='Test-Password-9821')
        cls.plan = VPSPlan.objects.create(name='Compute', description='A test plan', cpu=2,
            ram=4, storage=60, monthly_price=Decimal('299.00'), yearly_price=Decimal('2990.00'))

    def setUp(self):
        self.client.force_login(self.user)

    def review(self, cycle='MONTHLY', **extra):
        data = {'billing_cycle': cycle, 'operating_system': 'Ubuntu 26.04',
                'ssh_public_key': TEST_SSH_PUBLIC_KEY}
        data.update(extra)
        return self.client.post(reverse('select_plan', args=[self.plan.pk]), data)

    def checkout(self, cycle='MONTHLY', **extra):
        token = self.review(cycle).context['checkout_token']
        return self.client.post(reverse('order_confirm'), {'checkout_token': token, **extra})

    def other_order(self):
        order = Order.objects.create(customer=self.other.customer_profile, plan=self.plan,
            billing_cycle='MONTHLY', amount='299.00')
        Invoice.objects.create(order=order, invoice_number='OTHER-INVOICE', amount=order.amount,
                               due_date=timezone.now() + timedelta(days=1))
        return order

    def service_order(self, customer=None, status='ACTIVE', vmid='1006', ip='220.100.130.210'):
        customer = customer or self.user.customer_profile
        order = Order.objects.create(
            customer=customer, plan=self.plan, billing_cycle='MONTHLY', amount='299.00',
            status=status, provisioning_status='ACTIVE' if status == 'ACTIVE' else 'ACCEPTED',
            provisioning_vps_id='10', provisioning_vmid=vmid,
            provisioning_progress=100 if status == 'ACTIVE' else 42,
            provisioning_step='VPS is ready.' if status == 'ACTIVE' else 'Cloning template (42%)',
            provisioning_ip_address=ip if status == 'ACTIVE' else None,
            provisioning_payload={'os': 'Ubuntu 26.04'},
            ssh_username='vpsuser', ssh_public_key=TEST_SSH_PUBLIC_KEY,
        )
        Invoice.objects.create(
            order=order, invoice_number=f'SERVICE-{order.pk}', amount=order.amount,
            status=Invoice.Status.PAID, paid_at=timezone.now(),
            due_date=timezone.now() + timedelta(days=1),
        )
        if status == 'ACTIVE':
            Subscription.objects.create(
                customer=customer, order=order, status=Subscription.Status.ACTIVE,
                start_date=timezone.now(), next_billing_date=timezone.now() + timedelta(days=30),
            )
        return order

    def test_registration_creates_profile_and_logs_in(self):
        self.client.logout()
        response = self.client.post(reverse('register'), {'username': 'newcustomer',
            'password1': 'A-Strong-Password-9821', 'password2': 'A-Strong-Password-9821',
            'full_name': 'New Customer', 'email': 'new@example.com'})
        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(username='newcustomer')
        self.assertEqual(user.customer_profile.full_name, 'New Customer')
        self.assertEqual(user.email, 'new@example.com')
        self.assertEqual(Customer.objects.filter(user=user).count(), 1)

    def test_user_creation_also_creates_profile(self):
        self.assertEqual(self.user.customer_profile.full_name, 'alice')

    def test_legacy_user_gets_profile(self):
        self.user.customer_profile.delete()
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertTrue(Customer.objects.filter(user=self.user).exists())

    def test_anonymous_pages_are_protected(self):
        self.client.logout()
        for name, args in [('dashboard', []), ('my_vps', []), ('vps_detail', [1]),
            ('orders', []), ('invoices', []), ('account', []),
            ('select_plan', [self.plan.pk]), ('invoice', [1]), ('order_detail', [1]),
            ('order_confirm', [])]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 302)
        self.assertEqual(self.client.post(reverse('order_confirm')).status_code, 302)

    def test_login_redirects_dashboard_and_logout_requires_post(self):
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': 'alice', 'password': 'Test-Password-9821'})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('home'))

    def test_monthly_order_and_invoice(self):
        response = self.checkout()
        order = Order.objects.get()
        self.assertRedirects(response, reverse('invoice', args=[order.pk]))
        self.assertEqual(order.amount, self.plan.monthly_price)
        self.assertEqual(order.invoice.amount, order.amount)
        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.invoice.status, 'PENDING')
        self.assertEqual(order.invoice.invoice_number, f'INV-{order.pk:08d}')
        self.assertEqual(order.invoice.due_date, order.created_at + timedelta(days=1))
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(order.ssh_username, 'vpsuser')
        self.assertEqual(order.ssh_public_key, TEST_SSH_PUBLIC_KEY)

    def test_debian_operating_system_is_frozen_on_order(self):
        review = self.review(operating_system='Debian 13')
        self.assertEqual(review.status_code, 200)
        token = review.context['checkout_token']
        response = self.client.post(reverse('order_confirm'), {'checkout_token': token})
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(customer=self.user.customer_profile)
        self.assertEqual(order.operating_system, 'Debian 13')

    def test_yearly_order(self):
        self.checkout('YEARLY')
        self.assertEqual(Order.objects.get().amount, self.plan.yearly_price)
        self.assertEqual(Invoice.objects.get().amount, self.plan.yearly_price)

    def test_browser_cannot_set_amount_or_status_or_customer(self):
        review = self.review(amount='0.01', price='0.01')
        self.assertEqual(review.context['amount'], self.plan.monthly_price)
        self.client.post(reverse('order_confirm'), {'checkout_token': review.context['checkout_token'],
            'amount': '0.01', 'status': 'PAID', 'payment': 'success', 'customer': self.other.customer_profile.pk,
            'billing_cycle': 'YEARLY', 'plan_id': 999})
        order = Order.objects.get()
        self.assertEqual(order.customer, self.user.customer_profile)
        self.assertEqual(order.billing_cycle, 'MONTHLY')
        self.assertEqual(order.amount, self.plan.monthly_price)
        self.assertEqual(order.invoice.amount, order.amount)
        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.invoice.status, 'PENDING')

    def test_invalid_ssh_public_key_rejected(self):
        for key_value in ('', 'not-a-key', '-----BEGIN OPENSSH PRIVATE KEY-----'):
            with self.subTest(key=key_value):
                response = self.review(ssh_public_key=key_value)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_invalid_cycles_rejected(self):
        for cycle in ['weekly', '', 'monthly', 'YEARLY<script>']:
            with self.subTest(cycle=cycle):
                self.assertEqual(self.review(cycle).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_review_does_not_create_order(self):
        self.assertEqual(self.review().status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.client.get(reverse('order_confirm')).status_code, 405)

    def test_repeated_confirmation_creates_one_order_and_invoice(self):
        token = self.review().context['checkout_token']
        first = self.client.post(reverse('order_confirm'), {'checkout_token': token})
        second = self.client.post(reverse('order_confirm'), {'checkout_token': token})
        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_invoice_failure_rolls_back_order(self):
        token = self.review().context['checkout_token']
        with patch('portal.services.Invoice.objects.create', side_effect=IntegrityError('invoice failed')):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse('order_confirm'), {'checkout_token': token})
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Invoice.objects.exists())
        self.assertEqual(self.client.post(reverse('order_confirm'), {'checkout_token': token}).status_code, 302)

    def test_modified_missing_and_expired_tokens_rejected(self):
        token = self.review().context['checkout_token']
        for invalid in ['', token + 'tampered']:
            self.assertEqual(self.client.post(reverse('order_confirm'), {'checkout_token': invalid}).status_code, 400)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 3602):
            self.assertEqual(self.client.post(reverse('order_confirm'), {'checkout_token': token}).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_review_token_bound_to_account(self):
        token = self.review().context['checkout_token']
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('order_confirm'), {'checkout_token': token}).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_price_change_requires_review(self):
        token = self.review().context['checkout_token']
        VPSPlan.objects.filter(pk=self.plan.pk).update(monthly_price='399.00')
        response = self.client.post(reverse('order_confirm'), {'checkout_token': token})
        self.assertContains(response, 'price has changed', status_code=400)
        self.assertFalse(Order.objects.exists())

    def test_inactive_plan_cannot_be_purchased(self):
        token = self.review().context['checkout_token']
        VPSPlan.objects.filter(pk=self.plan.pk).update(is_active=False)
        self.assertNotContains(self.client.get(reverse('plans')), self.plan.name)
        self.assertEqual(self.client.get(reverse('select_plan', args=[self.plan.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('order_confirm'), {'checkout_token': token}).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_other_customers_order_is_hidden(self):
        order = self.other_order()
        self.assertEqual(self.client.get(reverse('order_detail', args=[order.pk])).status_code, 404)

    def test_other_customers_invoice_is_hidden(self):
        order = self.other_order()
        self.assertEqual(self.client.get(reverse('invoice', args=[order.pk])).status_code, 404)

    def test_order_list_is_scoped(self):
        other = self.other_order()
        self.checkout()
        response = self.client.get(reverse('orders'))
        self.assertEqual(list(response.context['page_obj']), list(Order.objects.filter(customer__user=self.user)))
        self.assertNotContains(response, 'OTHER-INVOICE')
        self.assertNotContains(response, reverse('order_detail', args=[other.pk]))

    def test_invoice_list_is_scoped(self):
        self.other_order()
        self.checkout()
        response = self.client.get(reverse('invoices'))
        self.assertEqual(list(response.context['page_obj']), list(Invoice.objects.filter(order__customer__user=self.user)))
        self.assertNotContains(response, 'OTHER-INVOICE')

    def test_dashboard_scopes_orders_and_subscriptions(self):
        other = self.other_order()
        Subscription.objects.create(customer=self.other.customer_profile, order=other,
            start_date=timezone.now(), next_billing_date=timezone.now() + timedelta(days=30))
        response = self.client.get(reverse('dashboard'))
        for key in ['order_count', 'pending_count', 'active_count']:
            self.assertEqual(response.context[key], 0)
        self.checkout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['order_count'], 1)
        self.assertEqual(response.context['pending_count'], 1)
        self.assertNotContains(response, 'OTHER-INVOICE')

    def test_my_vps_is_scoped_and_shows_connection_details(self):
        mine = self.service_order()
        other = self.service_order(customer=self.other.customer_profile, vmid='1007', ip='220.100.130.211')
        response = self.client.get(reverse('my_vps'))
        self.assertContains(response, 'My VPS')
        self.assertContains(response, mine.provisioning_ip_address)
        self.assertContains(response, reverse('vps_detail', args=[mine.pk]))
        self.assertNotContains(response, other.provisioning_ip_address)
        self.assertNotContains(response, reverse('vps_detail', args=[other.pk]))

    def test_vps_detail_is_scoped_and_shows_server_and_billing(self):
        mine = self.service_order()
        mine.ssh_host = 'proxmoxportal.dyndns.org'
        mine.ssh_port = 22015
        mine.save(update_fields=['ssh_host', 'ssh_port'])
        other = self.service_order(customer=self.other.customer_profile, vmid='1007', ip='220.100.130.211')
        response = self.client.get(reverse('vps_detail', args=[mine.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server overview')
        self.assertContains(response, mine.provisioning_ip_address)
        self.assertContains(response, 'ssh -p 22015 vpsuser@proxmoxportal.dyndns.org')
        self.assertContains(response, 'Ubuntu 26.04')
        self.assertEqual(self.client.get(reverse('vps_detail', args=[other.pk])).status_code, 404)

    def test_dashboard_surfaces_vps_management(self):
        mine = self.service_order()
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Your VPS servers')
        self.assertContains(response, mine.provisioning_ip_address)
        self.assertContains(response, 'Manage VPS')

    def test_dashboard_redesign_shows_real_data_and_states(self):
        self.user.customer_profile.full_name = 'Alice Example'
        self.user.customer_profile.save()
        active = self.service_order()
        provisioning = self.service_order(status='PROVISIONING', vmid='1008')
        self.other_order()
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'page-dashboard')
        self.assertContains(response, 'Welcome, Alice Example.')
        self.assertContains(response, 'dashboard.css')
        self.assertContains(response, f'VMID {active.provisioning_vmid}')
        self.assertContains(response, f'VMID {provisioning.provisioning_vmid}')
        self.assertContains(response, 'Provisioning')
        self.assertContains(response, 'Assigning...')
        self.assertContains(response, reverse('vps_detail', args=[provisioning.pk]))
        self.assertContains(response, active.invoice.invoice_number)
        self.assertNotContains(response, 'OTHER-INVOICE')

    def test_dashboard_name_falls_back_and_empty_states_render(self):
        Customer.objects.filter(pk=self.user.customer_profile.pk).update(full_name='')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Welcome, alice.')
        self.assertContains(response, 'No VPS servers yet.')
        self.assertContains(response, 'No orders yet.')

    def test_dashboard_styles_do_not_leak_to_other_pages(self):
        self.service_order()
        for name in ['my_vps', 'orders', 'invoices', 'account']:
            self.assertNotContains(self.client.get(reverse(name)), 'dashboard.css')
            self.assertNotContains(self.client.get(reverse(name)), 'page-dashboard')

    def test_account_update_only_changes_own_profile(self):
        self.client.post(reverse('account'), {'full_name': 'Alice Updated', 'company': 'Example',
            'phone': '123', 'user': self.other.pk, 'id': self.other.customer_profile.pk})
        self.user.customer_profile.refresh_from_db()
        self.other.customer_profile.refresh_from_db()
        self.assertEqual(self.user.customer_profile.full_name, 'Alice Updated')
        self.assertEqual(self.other.customer_profile.full_name, 'bob')

    def test_csrf_required_for_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name, args in [('order_confirm', []), ('select_plan', [self.plan.pk]),
                           ('account', []), ('logout', [])]:
            self.assertEqual(client.post(reverse(name, args=args), {}).status_code, 403)
        client.logout()
        self.assertEqual(client.post(reverse('register'), {}).status_code, 403)

    @override_settings(XENDIT_SECRET_API_KEY='', XENDIT_WEBHOOK_TOKEN='', XENDIT_BUSINESS_ID='', XENDIT_PUBLIC_BASE_URL='')
    def test_pages_render_and_empty_states(self):
        for name in ['home', 'dashboard', 'my_vps', 'plans', 'orders', 'invoices', 'account']:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(self.client.get(reverse('orders')), 'No orders yet')
        self.assertContains(self.client.get(reverse('invoices')), 'No invoices yet')
        self.checkout()
        order = Order.objects.get()
        self.assertEqual(self.client.get(reverse('order_detail', args=[order.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse('invoice', args=[order.pk])), 'Online payments are currently unavailable.')

    def test_missing_invoice_returns_404(self):
        order = Order.objects.create(customer=self.user.customer_profile, plan=self.plan,
                                    billing_cycle='MONTHLY', amount='299.00')
        self.assertEqual(self.client.get(reverse('invoice', args=[order.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse('orders')), 'Not issued')


class OrdersListingTests(TestCase):
    """Tabs, search, dropdown filters and pagination on the client My orders page (/orders/)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('alice', password='Test-Password-9821')
        cls.other = User.objects.create_user('bob', password='Test-Password-9821')
        cls.basic = VPSPlan.objects.create(name='VPS Basic', cpu=1, ram=2, storage=40,
            monthly_price=Decimal('999.00'), yearly_price=Decimal('9990.00'))
        cls.standard = VPSPlan.objects.create(name='VPS Standard', cpu=2, ram=4, storage=80,
            monthly_price=Decimal('1499.00'), yearly_price=Decimal('14990.00'))
        cls.secret = VPSPlan.objects.create(name='Bob Only Plan', cpu=4, ram=8, storage=160,
            monthly_price=Decimal('4999.00'), yearly_price=Decimal('49990.00'))
        # Oldest first, so the newest order (listed first) is the last entry.
        specs = [
            (cls.standard, 'MONTHLY', '1499.00', 'ACTIVE', '10.60.0.22'),
            (cls.standard, 'MONTHLY', '1499.00', 'ACTIVE', '10.60.0.23'),
            (cls.basic, 'MONTHLY', '999.00', 'ACTIVE', '10.60.0.25'),
            (cls.basic, 'MONTHLY', '999.00', 'ACTIVE', '10.60.0.26'),
            (cls.basic, 'YEARLY', '9990.00', 'ACTIVE', '10.60.0.27'),
            (cls.basic, 'MONTHLY', '999.00', 'PROVISIONING', None),
            (cls.standard, 'YEARLY', '14990.00', 'PROVISIONING', None),
            (cls.basic, 'MONTHLY', '999.00', 'PENDING', None),
            (cls.standard, 'MONTHLY', '1499.00', 'PENDING', None),
            (cls.basic, 'MONTHLY', '999.00', 'FAILED', None),
            (cls.basic, 'YEARLY', '9990.00', 'CANCELLED', None),
            (cls.standard, 'MONTHLY', '1499.00', 'PAID', None),
            (cls.basic, 'MONTHLY', '999.00', 'ACTIVE', '10.60.0.28'),
        ]
        cls.orders = []
        for index, (plan, cycle, amount, status, ip) in enumerate(specs):
            order = Order.objects.create(customer=cls.user.customer_profile, plan=plan, billing_cycle=cycle,
                amount=amount, status=status, provisioning_ip_address=ip)
            Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=len(specs) - index))
            cls.orders.append(order)
            if index != 8:  # order index 8 deliberately has no invoice
                Invoice.objects.create(order=order, invoice_number=f'INV-{order.pk:08d}', amount=amount,
                                       due_date=timezone.now() + timedelta(days=1))
        Order.objects.filter(pk=cls.orders[5].pk).update(provisioning_progress=42)
        Order.objects.filter(pk=cls.orders[9].pk).update(provisioning_vmid='2001')

        stranger = Order.objects.create(customer=cls.other.customer_profile, plan=cls.secret,
            billing_cycle='MONTHLY', amount='4999.00', status='ACTIVE', provisioning_ip_address='10.99.0.1')
        Invoice.objects.create(order=stranger, invoice_number='OTHER-INV-1', amount=stranger.amount,
                               due_date=timezone.now() + timedelta(days=1))
        cls.stranger = stranger

    def setUp(self):
        self.client.force_login(self.user)

    def listing(self, **params):
        return self.client.get(reverse('orders'), params)

    def all_ids(self, **params):
        first = self.listing(**params)
        ids = []
        for number in range(1, first.context['page_obj'].paginator.num_pages + 1):
            ids += [order.pk for order in self.listing(**params, page=number).context['page_obj']]
        return ids

    def pk(self, index):
        return self.orders[index].pk

    # ----- pagination and counts -----
    def test_first_page_has_five_newest_orders_and_accurate_range(self):
        response = self.listing()
        self.assertEqual([o.pk for o in response.context['page_obj']], [self.pk(i) for i in (12, 11, 10, 9, 8)])
        self.assertEqual(response.context['total_count'], 13)
        self.assertContains(response, 'Showing 1 – 5 of 13 orders')
        self.assertEqual(response.context['page_obj'].paginator.num_pages, 3)

    def test_last_page_range_and_rows(self):
        response = self.listing(page=3)
        self.assertEqual(len(response.context['page_obj']), 3)
        self.assertContains(response, 'Showing 11 – 13 of 13 orders')

    def test_out_of_range_and_garbage_page_fall_back_safely(self):
        self.assertContains(self.listing(page=99), 'Showing 11 – 13 of 13 orders')
        self.assertContains(self.listing(page='abc'), 'Showing 1 – 5 of 13 orders')

    def test_single_result_uses_singular(self):
        response = self.listing(q='INV-%08d' % self.pk(6))
        self.assertContains(response, 'Showing 1 – 1 of 1 order')
        self.assertNotContains(response, 'of 1 orders')
        self.assertNotContains(response, 'aria-label="Pagination"')

    def test_page_links_are_elided_and_mark_current_page(self):
        response = self.listing(page=2)
        self.assertContains(response, 'aria-current="page" aria-label="Page 2, current page"')
        self.assertEqual([link.get('number') for link in response.context['page_links']], [1, 2, 3])

    # ----- status tabs -----
    def test_tabs_map_to_existing_statuses(self):
        expected = {'active': ('ACTIVE', 6), 'provisioning': ('PROVISIONING', 2), 'pending': ('PENDING', 2),
                    'paid': ('PAID', 1), 'failed': ('FAILED', 1), 'cancelled': ('CANCELLED', 1)}
        for key, (status, count) in expected.items():
            with self.subTest(tab=key):
                ids = self.all_ids(status=key)
                self.assertEqual(len(ids), count)
                self.assertEqual(set(Order.objects.filter(pk__in=ids).values_list('status', flat=True)), {status})

    def test_pending_payment_tab_uses_existing_pending_status_only(self):
        self.assertFalse(any(value == 'PENDING_PAYMENT' for value, _ in Order.Status.choices))
        response = self.listing(status='pending')
        self.assertContains(response, 'Pending payment')
        self.assertEqual(response.context['total_count'], Order.objects.filter(
            customer__user=self.user, status=Order.Status.PENDING).count())

    def test_tab_total_spans_all_pages_not_just_the_displayed_one(self):
        self.assertEqual(self.listing(status='active').context['total_count'], 6)
        page_two = self.listing(status='active', page=2)
        self.assertEqual(len(page_two.context['page_obj']), 1)
        self.assertContains(page_two, 'Showing 6 – 6 of 6 orders')

    def test_failed_cancelled_and_paid_tabs_appear_only_when_relevant(self):
        keys = [tab['key'] for tab in self.listing().context['tabs']]
        self.assertEqual(keys, ['all', 'active', 'provisioning', 'pending', 'paid', 'failed', 'cancelled'])
        newcomer = User.objects.create_user('dana', password='Test-Password-9821')
        Order.objects.create(customer=newcomer.customer_profile, plan=self.basic, billing_cycle='MONTHLY',
                             amount='999.00', status='ACTIVE')
        self.client.force_login(newcomer)
        self.assertEqual([tab['key'] for tab in self.listing().context['tabs']],
                         ['all', 'active', 'provisioning', 'pending'])

    def test_current_tab_is_marked_and_invalid_status_is_ignored(self):
        response = self.listing(status='provisioning')
        current = [tab['key'] for tab in response.context['tabs'] if tab['current']]
        self.assertEqual(current, ['provisioning'])
        ignored = self.listing(status='bogus')
        self.assertEqual(ignored.context['total_count'], 13)
        self.assertEqual([tab['key'] for tab in ignored.context['tabs'] if tab['current']], ['all'])

    # ----- search -----
    def test_search_by_order_number_with_and_without_hash(self):
        target = self.pk(11)
        self.assertEqual(self.all_ids(q=f'#{target}'), [target])
        self.assertIn(target, self.all_ids(q=str(target)))

    def test_search_by_plan_name_is_case_insensitive(self):
        ids = self.all_ids(q='vps standard')
        self.assertEqual(set(ids), {self.pk(i) for i in (0, 1, 6, 8, 11)})

    def test_search_by_ip_address_exact_and_partial(self):
        self.assertEqual(self.all_ids(q='10.60.0.27'), [self.pk(4)])
        self.assertEqual(set(self.all_ids(q='10.60.0.2')), {self.pk(i) for i in (0, 1, 2, 3, 4, 12)})

    def test_search_by_invoice_number(self):
        self.assertEqual(self.all_ids(q='INV-%08d' % self.pk(6)), [self.pk(6)])

    def test_search_covers_every_page_of_results(self):
        ids = self.all_ids(q='10.60')
        self.assertEqual(len(ids), 6)
        self.assertEqual(self.listing(q='10.60').context['total_count'], 6)
        self.assertEqual(len(self.listing(q='10.60', page=2).context['page_obj']), 1)

    # ----- dropdown filters and combinations -----
    def test_plan_and_cycle_filters(self):
        self.assertEqual(set(self.all_ids(plan=self.standard.pk)), {self.pk(i) for i in (0, 1, 6, 8, 11)})
        self.assertEqual(set(self.all_ids(cycle='YEARLY')), {self.pk(i) for i in (4, 6, 10)})

    def test_all_filters_combine(self):
        self.assertEqual(set(self.all_ids(status='active', plan=self.basic.pk, cycle='MONTHLY', q='10.60')),
                         {self.pk(i) for i in (2, 3, 12)})
        self.assertEqual(self.all_ids(status='provisioning', plan=self.standard.pk, cycle='YEARLY'), [self.pk(6)])
        self.assertEqual(self.all_ids(status='failed', cycle='YEARLY'), [])

    def test_invalid_filter_values_are_ignored(self):
        for params in ({'plan': 'abc'}, {'plan': self.secret.pk}, {'plan': '99999999999999999999'},
                       {'cycle': 'weekly'}, {'q': 'x' * 500}, {'q': '   '}):
            with self.subTest(params=params):
                response = self.listing(**params)
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.listing(plan=self.secret.pk).context['total_count'], 13)
        self.assertEqual(self.listing(cycle='weekly').context['total_count'], 13)
        self.assertEqual(self.listing(q='   ').context['total_count'], 13)

    def test_filter_options_list_only_the_customers_own_plans(self):
        response = self.listing()
        self.assertEqual([option['name'] for option in response.context['plan_options']], ['VPS Basic', 'VPS Standard'])
        self.assertNotContains(response, 'Bob Only Plan')

    # ----- links keep the filters -----
    def test_pagination_and_tab_links_preserve_filters(self):
        response = self.listing(status='active', q='10.60', plan=self.basic.pk, cycle='MONTHLY')
        self.assertEqual(response.context['total_count'], 3)
        response = self.listing(status='active', q='10.60')
        self.assertEqual(response.context['next_url'], '/orders/?status=active&q=10.60&page=2')
        self.assertContains(response, 'href="/orders/?status=active&amp;q=10.60&amp;page=2"')
        tabs = {tab['key']: tab['url'] for tab in response.context['tabs']}
        self.assertEqual(tabs['provisioning'], '/orders/?status=provisioning&q=10.60')
        self.assertEqual(tabs['all'], '/orders/?q=10.60')
        previous = self.listing(status='active', q='10.60', page=2).context['previous_url']
        self.assertEqual(previous, '/orders/?status=active&q=10.60')

    def test_search_text_is_url_encoded_in_links(self):
        response = self.listing(q='vps basic')
        self.assertEqual(response.context['total_count'], 8)
        self.assertEqual(response.context['next_url'], '/orders/?q=vps+basic&page=2')

    def test_toolbar_keeps_selected_values(self):
        response = self.listing(status='active', q='10.60', plan=self.basic.pk, cycle='YEARLY')
        self.assertContains(response, 'value="10.60"')
        self.assertContains(response, f'<option value="{self.basic.pk}" selected>VPS Basic</option>', html=True)
        self.assertContains(response, '<option value="YEARLY" selected>Yearly</option>', html=True)
        self.assertContains(response, '<input type="hidden" name="status" value="active">', html=True)

    # ----- rendering of real data -----
    def test_rows_show_real_customer_data(self):
        yearly = self.orders[4]
        response = self.listing(q=f'#{yearly.pk}')
        self.assertContains(response, '₱9,990.00')
        self.assertContains(response, 'Yearly')
        self.assertContains(response, '<code>10.60.0.27</code>', html=True)
        self.assertContains(response, f'href="{reverse("invoice", args=[yearly.pk])}"')
        self.assertContains(response, f'INV-{yearly.pk:08d}')
        self.assertContains(response, f'href="{reverse("order_detail", args=[yearly.pk])}"')
        self.assertContains(response, 'Active')

    def test_provisioning_vmid_pending_and_missing_invoice_states(self):
        provisioning = self.listing(status='provisioning')
        self.assertContains(provisioning, '42% provisioning')
        self.assertContains(provisioning, '<progress value="42" max="100"')
        self.assertContains(self.listing(status='failed'), 'VMID 2001')
        pending = self.listing(status='pending')
        self.assertContains(pending, 'Pending payment')
        self.assertContains(pending, 'Not issued')

    def test_ip_unavailable_state_renders_dash(self):
        response = self.listing(status='cancelled')
        self.assertContains(response, 'title="No address assigned yet"')

    # ----- empty states -----
    def test_no_matching_orders_shows_filtered_empty_state(self):
        response = self.listing(q='zzz-no-such-order')
        self.assertContains(response, 'No orders match your filters.')
        self.assertContains(response, 'Clear filters')
        self.assertContains(response, 'data-orders-filter')
        self.assertNotContains(response, 'Showing ')
        self.assertEqual(response.context['total_count'], 0)

    def test_customer_without_orders_sees_first_order_empty_state(self):
        newcomer = User.objects.create_user('erin', password='Test-Password-9821')
        self.client.force_login(newcomer)
        response = self.listing()
        self.assertContains(response, 'No orders yet.')
        self.assertContains(response, 'Explore plans')
        self.assertContains(response, f'href="{reverse("plans")}"')
        self.assertNotContains(response, 'data-orders-filter')
        self.assertNotContains(response, 'Filter orders by status')

    # ----- ownership, auth, scope -----
    def test_other_customers_orders_never_appear(self):
        self.assertEqual(self.all_ids(q='10.99'), [])
        self.assertEqual(self.all_ids(q='OTHER-INV'), [])
        response = self.listing(q=f'#{self.stranger.pk}')
        self.assertEqual(response.context['total_count'], 0)
        self.assertNotContains(response, reverse('order_detail', args=[self.stranger.pk]))
        self.assertNotIn(self.stranger.pk, self.all_ids())

    def test_authentication_methods_and_staff_rules_are_unchanged(self):
        self.client.logout()
        self.assertEqual(self.listing().status_code, 302)
        staff = User.objects.create_user('staffer', password='Test-Password-9821', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.listing().status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('orders')).status_code, 405)

    def test_orders_assets_are_scoped_to_this_page(self):
        response = self.listing()
        self.assertContains(response, 'portal/orders.css')
        self.assertContains(response, 'portal/orders.js')
        self.assertContains(response, 'page-orders')
        self.assertContains(response, 'Create VPS')
        self.assertContains(response, f'href="{reverse("plans")}"')
        self.assertNotContains(response, 'dashboard.css')
        for name in ['dashboard', 'my_vps', 'invoices', 'account']:
            with self.subTest(page=name):
                other = self.client.get(reverse(name))
                self.assertNotContains(other, 'orders.css')
                self.assertNotContains(other, 'orders.js')
                self.assertNotContains(other, 'page-orders')

    def test_query_count_does_not_grow_with_rows(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            self.listing()
        self.assertLess(len(queries), 15)
