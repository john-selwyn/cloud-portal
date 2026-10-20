from django.conf import settings
from django.core.checks import Error, register
from .xendit import configured


@register()
def xendit_configuration(app_configs, **kwargs):
    values = (settings.XENDIT_SECRET_API_KEY, settings.XENDIT_WEBHOOK_TOKEN,
              settings.XENDIT_BUSINESS_ID, settings.XENDIT_PUBLIC_BASE_URL)
    if any(values) and not configured():
        return [Error('Xendit requires all four XENDIT settings and an HTTPS public origin.', id='portal.E001')]
    return []


@register()
def customer_email_configuration(app_configs, **kwargs):
    errors = []
    import ipaddress
    try:
        for value in settings.CUSTOMER_TRUSTED_PROXY_IPS:
            ipaddress.ip_address(value)
    except ValueError:
        errors.append(Error('Trusted account proxies must be exact IP addresses.', id='portal.E013'))
    if settings.CUSTOMER_REQUIRE_EMAIL_VERIFICATION and not settings.CUSTOMER_EMAIL_ENABLED:
        errors.append(Error('Required email verification needs enabled mail delivery.', id='portal.E010'))
    if settings.CUSTOMER_EMAIL_ENABLED:
        from .customer_security import email_origin
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            email_origin()
            validate_email(settings.DEFAULT_FROM_EMAIL)
        except (ValueError, ValidationError):
            errors.append(Error('Customer mail needs a valid sender and canonical HTTPS origin.', id='portal.E011'))
        config = settings.MAILERS.get('default', {})
        opts = config.get('OPTIONS', {})
        if (config.get('BACKEND') != 'django.core.mail.backends.smtp.EmailBackend'
                or not opts.get('host') or bool(opts.get('use_tls')) == bool(opts.get('use_ssl'))):
            errors.append(Error('Customer mail needs an SMTP host and exactly one of TLS or SSL.', id='portal.E012'))
    return errors
