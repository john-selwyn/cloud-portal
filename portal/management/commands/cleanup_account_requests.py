from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from portal.models import AccountRequestLimit, CustomerEmail


class Command(BaseCommand):
    help = 'Remove expired hashed request limits and unconfirmed email requests; retain users and verified emails.'

    def handle(self, *args, **options):
        now = timezone.now()
        limits, _ = AccountRequestLimit.objects.filter(expires_at__lte=now).delete()
        pending, _ = CustomerEmail.objects.filter(verified_at__isnull=True, requested_at__lte=
            now - timedelta(seconds=settings.CUSTOMER_EMAIL_TOKEN_TIMEOUT)).delete()
        self.stdout.write(f'Removed {limits} expired limits and {pending} pending email requests. No accounts removed.')
