"""Filtering, search and pagination for the customer "My orders" page (/orders/).

Everything here works on the signed-in customer's full order set, never on the rows of the
current page, and never changes data. No model fields or statuses are added: every tab maps
to an existing Order.Status value.

Query parameters (all optional, all validated; unknown values are ignored):
    status  all | active | provisioning | pending | paid | failed | cancelled
    q       free-text search: order number, plan name, IP address or invoice number
    plan    id of a plan the customer has ordered
    cycle   MONTHLY | YEARLY
    page    page number
"""
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from .models import Order, VPSPlan

PAGE_SIZE = 5
MAX_SEARCH_LENGTH = 100

# (tab key, label, Order.status). "Pending payment" is the existing PENDING state: an order that
# has been created but whose payment has not been verified yet. No new status is introduced.
PRIMARY_TABS = (
    ('all', 'All orders', None),
    ('active', 'Active', Order.Status.ACTIVE),
    ('provisioning', 'Provisioning', Order.Status.PROVISIONING),
    ('pending', 'Pending payment', Order.Status.PENDING),
)
# Remaining statuses. Their tabs appear only when the customer has orders in that state (or one is
# selected), so every existing status stays reachable without crowding the common view.
EXTRA_TABS = (
    ('paid', 'Paid', Order.Status.PAID),
    ('failed', 'Failed', Order.Status.FAILED),
    ('cancelled', 'Cancelled', Order.Status.CANCELLED),
)
STATUS_BY_KEY = {key: status for key, _label, status in PRIMARY_TABS + EXTRA_TABS}


def customer_orders(user):
    return Order.objects.filter(customer__user=user)


def parse_filters(params, plan_ids):
    """Return a clean filters dict from raw GET parameters."""
    status = params.get('status', 'all')
    if status not in STATUS_BY_KEY:
        status = 'all'
    term = ' '.join(params.get('q', '').split())[:MAX_SEARCH_LENGTH]
    plan = params.get('plan', '')
    plan = int(plan) if plan.isascii() and plan.isdigit() and int(plan) in plan_ids else None
    cycle = params.get('cycle', '')
    if cycle not in Order.BillingCycle.values:
        cycle = ''
    return {'status': status, 'q': term, 'plan': plan, 'cycle': cycle}


def search_condition(term):
    """Match order number (with or without '#'), plan name, IP address or invoice number."""
    condition = (
        Q(plan__name__icontains=term)
        | Q(provisioning_ip_address__icontains=term)
        | Q(invoice__invoice_number__icontains=term)
    )
    number = term.lstrip('#').strip()
    if number.isascii() and number.isdigit() and len(number) <= 18:
        condition |= Q(pk=int(number))
    return condition


def apply_filters(queryset, filters):
    status = STATUS_BY_KEY[filters['status']]
    if status:
        queryset = queryset.filter(status=status)
    if filters['plan']:
        queryset = queryset.filter(plan_id=filters['plan'])
    if filters['cycle']:
        queryset = queryset.filter(billing_cycle=filters['cycle'])
    if filters['q']:
        queryset = queryset.filter(search_condition(filters['q']))
    return queryset


def query_string(filters, *, status=None, page=None):
    """Encode the active filters (optionally overriding status/page) for a link."""
    status = filters['status'] if status is None else status
    items = []
    if status != 'all':
        items.append(('status', status))
    if filters['q']:
        items.append(('q', filters['q']))
    if filters['plan']:
        items.append(('plan', filters['plan']))
    if filters['cycle']:
        items.append(('cycle', filters['cycle']))
    if page and page > 1:
        items.append(('page', page))
    return urlencode(items)


def listing_url(filters, **kwargs):
    query = query_string(filters, **kwargs)
    return f"{reverse('orders')}?{query}" if query else reverse('orders')


def build_orders_context(user, params):
    base = customer_orders(user)
    present_statuses = set(base.values_list('status', flat=True).distinct())
    plans = list(VPSPlan.objects.filter(pk__in=base.values('plan_id')).order_by('name'))
    filters = parse_filters(params, {plan.pk for plan in plans})

    records = apply_filters(base, filters).select_related('plan', 'invoice').order_by('-created_at', '-pk')
    paginator = Paginator(records, PAGE_SIZE)
    page_obj = paginator.get_page(params.get('page'))

    tabs = []
    for key, label, status in PRIMARY_TABS + EXTRA_TABS:
        is_extra = (key, label, status) in EXTRA_TABS
        if is_extra and status not in present_statuses and filters['status'] != key:
            continue
        tabs.append({
            'key': key,
            'label': label,
            'url': listing_url(filters, status=key),
            'current': filters['status'] == key,
            'dot': key if key != 'all' else '',
        })

    page_links = []
    if paginator.count:
        for entry in paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1):
            if entry == paginator.ELLIPSIS:
                page_links.append({'ellipsis': True})
            else:
                page_links.append({
                    'number': entry,
                    'url': listing_url(filters, page=entry),
                    'current': entry == page_obj.number,
                })

    narrowed = bool(filters['q'] or filters['plan'] or filters['cycle'] or filters['status'] != 'all')
    return {
        'page_obj': page_obj,
        'filters': filters,
        'tabs': tabs,
        'plan_options': [{'pk': plan.pk, 'name': plan.name, 'selected': plan.pk == filters['plan']} for plan in plans],
        'cycle_options': [{'value': value, 'label': label, 'selected': value == filters['cycle']}
                          for value, label in Order.BillingCycle.choices],
        'page_links': page_links,
        'previous_url': listing_url(filters, page=page_obj.previous_page_number()) if page_obj.has_previous() else '',
        'next_url': listing_url(filters, page=page_obj.next_page_number()) if page_obj.has_next() else '',
        'total_count': paginator.count,
        'showing_start': page_obj.start_index() if paginator.count else 0,
        'showing_end': page_obj.end_index() if paginator.count else 0,
        'has_orders': bool(present_statuses),
        'filters_active': narrowed,
        'clear_url': reverse('orders'),
    }
