"""Customer email ownership and shared, database-backed request limits."""
from datetime import timedelta
from urllib.parse import urlsplit
import logging
import ipaddress
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.urls import reverse

from .models import AccountRequestLimit, CustomerEmail

logger = logging.getLogger(__name__)
EMAIL_SALT = "portal.customer-email.v1"


def normalize_email(value):
    return value.strip().lower()


def email_available(email, user=None):
    users = User.objects.filter(email__iexact=email)
    claims = CustomerEmail.objects.filter(email=email)
    if user is not None:
        users = users.exclude(pk=user.pk)
        claims = claims.exclude(user=user)
    # Expired pending requests don't reserve an otherwise unused address forever.
    claims = claims.filter(verified_at__isnull=False) | claims.filter(
        requested_at__gt=timezone.now() - timedelta(seconds=settings.CUSTOMER_EMAIL_TOKEN_TIMEOUT))
    return not users.exists() and not claims.exists()


def verified_email(user):
    return CustomerEmail.objects.filter(user=user, email=normalize_email(user.email),
                                        verified_at__isnull=False).exists()


def email_origin():
    origin = settings.CUSTOMER_PUBLIC_ORIGIN.rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("A canonical HTTPS customer origin is required.")
    return origin


def request_allowed(request, action, identity="", limit=5, seconds=3600):
    """Count across web workers; never trust client-supplied forwarding headers.

    Store only keyed hashes of identities/IPs. Successful requests count too.
    A fixed window bounds repeated mail/password attempts without permanent locks.
    """
    allowed = True
    now = timezone.now()
    remote = request.META.get("REMOTE_ADDR", "unknown")
    # Only an explicitly trusted proxy may supply a single X-Real-IP value.
    # Nginx must overwrite that header, and Gunicorn must not be publicly reachable.
    if remote in settings.CUSTOMER_TRUSTED_PROXY_IPS:
        try:
            remote = str(ipaddress.ip_address(request.META.get("HTTP_X_REAL_IP", "")))
        except ValueError:
            pass
    identities = [("ip", remote)]
    if identity:
        identities.append(("identity", str(identity).lower()))
    for kind, value in identities:
        key = salted_hmac("portal.request-limit", f"{action}:{kind}:{value}").hexdigest()
        with transaction.atomic():
            row, _ = AccountRequestLimit.objects.select_for_update().get_or_create(
                key=key, defaults={"expires_at": now + timedelta(seconds=seconds)})
            if row.expires_at <= now:
                row.count = 0
                row.expires_at = now + timedelta(seconds=seconds)
            row.count += 1
            row.save(update_fields=["count", "expires_at"])
            maximum = limit * 10 if kind == "ip" and identity else limit
            allowed = allowed and row.count <= maximum
    return allowed


def prepare_email(user, email):
    """Caller holds the user lock. A unique address claim serializes races."""
    email = normalize_email(email)
    cutoff = timezone.now() - timedelta(seconds=settings.CUSTOMER_EMAIL_TOKEN_TIMEOUT)
    CustomerEmail.objects.filter(email=email, verified_at__isnull=True,
                                 requested_at__lte=cutoff).delete()
    if not email_available(email, user):
        raise ValueError("This email address cannot be used. Choose another address or recover your account.")
    CustomerEmail.objects.filter(user=user, verified_at__isnull=True).exclude(email=email).delete()
    row, _ = CustomerEmail.objects.get_or_create(user=user, email=email)
    row.nonce = uuid.uuid4()
    row.original_email = normalize_email(user.email)
    row.auth_hash = user.get_session_auth_hash()
    row.requested_at = timezone.now()
    row.save()
    return row


def send_verification(row):
    """Never log email contents, links, recipients or SMTP exception details."""
    if not settings.CUSTOMER_EMAIL_ENABLED:
        return False
    token = signing.dumps({"id": row.pk, "nonce": str(row.nonce)}, salt=EMAIL_SALT)
    url = email_origin() + reverse("verify_email", args=[token])
    try:
        return send_mail(
            "Confirm your Cloud Portal email",
            "Confirm this email address for your ICT Ventures Cloud Portal account:\n\n"
            + url + "\n\nThis link expires in one hour by default. Open it and confirm to continue. "
            "If you did not request this, ignore this email. Your current email remains unchanged.",
            settings.DEFAULT_FROM_EMAIL, [row.email],
        ) == 1
    except Exception:
        logger.warning("Customer verification delivery failed; check mail service privately.")
        return False


def confirm_email(token, apply=False):
    """GET previews; CSRF-protected POST consumes the one-time token."""
    try:
        payload = signing.loads(token, salt=EMAIL_SALT, max_age=settings.CUSTOMER_EMAIL_TOKEN_TIMEOUT)
        with transaction.atomic():
            # Consistent lock order: user, then address; avoid change/confirm deadlocks.
            candidate = CustomerEmail.objects.get(pk=payload["id"], verified_at__isnull=True)
            user = User.objects.select_for_update().get(pk=candidate.user_id)
            row = CustomerEmail.objects.select_for_update().get(pk=candidate.pk, verified_at__isnull=True)
            if (not user.is_active or user.is_staff or user.is_superuser
                    or str(row.nonce) != payload["nonce"]
                    or not constant_time_compare(row.auth_hash, user.get_session_auth_hash())
                    or row.original_email != normalize_email(user.email)
                    or row.requested_at <= timezone.now() - timedelta(seconds=settings.CUSTOMER_EMAIL_TOKEN_TIMEOUT)
                    or not email_available(row.email, user)):
                return False
            if apply:
                user.email = row.email
                user.save(update_fields=["email"])
                row.verified_at = timezone.now()
                row.auth_hash = ""
                row.save(update_fields=["verified_at", "auth_hash"])
                CustomerEmail.objects.filter(user=user).exclude(pk=row.pk).delete()
            return True
    except (signing.BadSignature, KeyError, TypeError, ValueError, User.DoesNotExist,
            CustomerEmail.DoesNotExist, IntegrityError):
        return False
