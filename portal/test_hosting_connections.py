from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Customer, HostingAccount


class HostingConnectionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user('portal-alice')
        cls.bob = User.objects.create_user('portal-bob')
        cls.staff = User.objects.create_user('staff', is_staff=True)
        cls.customer = Customer.objects.get_or_create(user=cls.alice, defaults={'full_name': 'Alice'})[0]
        bob = Customer.objects.get_or_create(user=cls.bob, defaults={'full_name': 'Bob'})[0]
        cls.account = HostingAccount.objects.create(customer=cls.customer, username='hostalice',
            domain='alice.example.com', package='business', shell='jailbash', verified_at=timezone.now())
        cls.other = HostingAccount.objects.create(customer=bob, username='hostbob',
            domain='bob.example.com', package='starter', shell='nologin', verified_at=timezone.now())

    def test_requires_customer_login(self):
        self.assertEqual(self.client.get(reverse('my_hosting')).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('my_hosting')).status_code, 403)

    def test_lists_only_owned_accounts_and_actual_hosting_username(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('my_hosting'))
        self.assertContains(response, 'hostalice@proxmo-2.dyndns.org')
        self.assertContains(response, 'ssh -p 2222')
        self.assertNotContains(response, 'hostbob')
        self.assertNotContains(response, 'bob.example.com')
        self.assertIn('no-store', response['Cache-Control'])

    def test_welcome_is_owner_scoped_and_downloadable(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('hosting_welcome', args=[self.account.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertContains(response, 'No password is included')
        self.assertContains(response, '/home/hostalice/web/alice.example.com/public_html')
        self.assertEqual(self.client.get(reverse('hosting_welcome', args=[self.other.pk])).status_code, 404)

    def test_sftp_only_account_gets_no_ssh_command(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('my_hosting'))
        self.assertContains(response, 'SFTP only')
        self.assertContains(response, 'sftp -P 2222')
        self.assertNotContains(response, 'ssh -p 2222')
        response = self.client.get(reverse('hosting_welcome', args=[self.other.pk]))
        self.assertNotContains(response, 'SSH command:')

    def test_inactive_account_hidden_and_download_denied(self):
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        self.client.force_login(self.alice)
        self.assertNotContains(self.client.get(reverse('my_hosting')), 'hostalice')
        self.assertEqual(self.client.get(reverse('hosting_welcome', args=[self.account.pk])).status_code, 404)

    def test_empty_state_does_not_guess_username(self):
        user = User.objects.create_user('unlinked')
        self.client.force_login(user)
        response = self.client.get(reverse('my_hosting'))
        self.assertContains(response, 'No hosting accounts linked yet')
        self.assertNotContains(response, 'unlinked@proxmo-2')

    def test_rejects_shell_or_path_injection_in_mapping(self):
        self.account.username = 'alice;whoami'
        with self.assertRaises(ValidationError):
            self.account.full_clean()
        self.account.username = 'hostalice'
        self.account.domain = '../another-account'
        with self.assertRaises(ValidationError):
            self.account.full_clean()

    def test_customer_cannot_mutate_mapping_through_page(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('my_hosting'), {'username': 'hostbob'})
        self.assertEqual(response.status_code, 405)
        self.account.refresh_from_db()
        self.assertEqual(self.account.username, 'hostalice')
