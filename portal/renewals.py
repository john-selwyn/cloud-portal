"""Renewal invoices only. No payments, entitlement updates, messages or VM calls."""
import calendar
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.models import ADDITION, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Invoice, Order, Subscription
from .provisioning import require_paid


def lead_days():
    value = settings.RENEWAL_INVOICE_LEAD_DAYS
    if type(value) is not int or not 0 <= value <= 90:
        raise ValidationError("Renewal invoice lead time must be between 0 and 90 days.")
    return value


def period_end(subscription):
    """Advance the stored boundary while retaining the original UTC anniversary."""
    start = subscription.next_billing_date.astimezone(timezone.get_default_timezone())
    anchor = subscription.start_date.astimezone(timezone.get_default_timezone())
    months = 12 if subscription.renewal_cycle == Order.BillingCycle.YEARLY else 1
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    month += 1
    return start.replace(year=year, month=month,
                         day=min(anchor.day, calendar.monthrange(year, month)[1]))


def agreement(subscription):
    return {"amount": str(subscription.renewal_amount), "cycle": subscription.renewal_cycle,
            "currency": subscription.renewal_currency, "anchor": subscription.start_date.isoformat(),
            "customer": subscription.customer_id}


def review(subscription, *, now=None):
    """Read-only proposal; eligibility is checked again under lock at creation."""
    now = now or timezone.now()
    existing = subscription.renewal_invoices.filter(period_start=subscription.next_billing_date).first()
    result = {"subscription": subscription, "invoice": existing,
              "due": subscription.next_billing_date, "amount": subscription.renewal_amount,
              "currency": subscription.renewal_currency, "eligible": False, "reason": ""}
    if existing:
        result["reason"] = "Invoice already issued for this period."
    elif subscription.status != Subscription.Status.ACTIVE or subscription.order.status != Order.Status.ACTIVE:
        result["reason"] = "Service is not active; review individually."
    elif subscription.customer_id != subscription.order.customer_id:
        result["reason"] = "Subscription ownership needs review."
    elif (subscription.renewal_amount is None or subscription.renewal_amount <= 0
          or subscription.renewal_cycle not in Order.BillingCycle.values
          or subscription.renewal_currency != "PHP"):
        result["reason"] = "Original billing agreement needs review."
    elif subscription.start_date >= subscription.next_billing_date:
        result["reason"] = "Billing dates need review."
    elif subscription.next_billing_date.day != min(subscription.start_date.day, calendar.monthrange(
            subscription.next_billing_date.year, subscription.next_billing_date.month)[1]):
        result["reason"] = "Billing anniversary needs review."
    elif subscription.next_billing_date <= now:
        result["reason"] = "Already due or overdue; individual review required."
    elif subscription.next_billing_date > now + timedelta(days=lead_days()):
        result["reason"] = "Outside the invoice preparation window."
    else:
        result.update(eligible=True, end=period_end(subscription), reason="Ready for invoice review.")
    return result


@transaction.atomic
def generate_invoice(subscription_id, *, actor, expected_due, expected_agreement=None):
    """Explicit, audited, repeat-safe generation for one reviewed next period."""
    if not actor or not actor.is_active or not actor.is_staff or not actor.is_superuser:
        raise PermissionDenied("Only an active administrator can issue renewal invoices.")
    if not settings.RENEWAL_INVOICING_ENABLED:
        raise ValidationError("Renewal invoice generation is disabled.")
    # Match provisioning/payment lock order: order, subscription, invoice.
    order_id = Subscription.objects.values_list("order_id", flat=True).get(pk=subscription_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
    subscription.order = order
    if subscription.next_billing_date != expected_due:
        raise ValidationError("The billing date changed. Review this renewal again.")
    if expected_agreement is not None and agreement(subscription) != expected_agreement:
        raise ValidationError("The billing agreement changed. Review this renewal again.")
    proposal = review(subscription)
    if proposal["invoice"]:
        return proposal["invoice"], False
    if not proposal["eligible"]:
        raise ValidationError(proposal["reason"])
    require_paid(order)
    # Database uniqueness also protects against an unexpected concurrent writer.
    invoice, created = Invoice.objects.get_or_create(
        subscription=subscription, purpose=Invoice.Purpose.RENEWAL,
        period_start=subscription.next_billing_date,
        defaults={"order": order, "invoice_number": "REN-" + uuid.uuid4().hex.upper(),
                  "amount": subscription.renewal_amount, "currency": subscription.renewal_currency,
                  "period_end": proposal["end"], "due_date": subscription.next_billing_date,
                  "status": Invoice.Status.PENDING},
    )
    if created:
        LogEntry.objects.log_actions(user_id=actor.pk, queryset=Invoice.objects.filter(pk=invoice.pk),
            action_flag=ADDITION, change_message="Issued one reviewed renewal invoice; no payment or service change.")
    return invoice, created
