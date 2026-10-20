"""Filtering, search and pagination for the customer "My invoices" page (/invoices/).

Everything works on the signed-in customer's full invoice set (never just the displayed page)
and never changes data. No model fields, statuses or migrations are added.

Query parameters (all optional and validated; unknown values are ignored):
    status  all | pending | paid | overdue | void
    q       free-text search: invoice number or order number
    due     today | next7 | month | last30 | older
    page    page number

"Overdue" is derived, never stored by this page: an invoice that is still unpaid (stored status
PENDING or OVERDUE) and whose due date has passed. A PAID or VOID invoice is never overdue.
Date ranges use the application's current time zone.
"""
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Case, CharField, F, Q, Value, When
from django.urls import reverse
from django.utils import timezone

from .models import Invoice

PAGE_SIZE = 5
MAX_SEARCH_LENGTH = 100
UNPAID = (Invoice.Status.PENDING, Invoice.Status.OVERDUE)

# (key, label, effective status). Effective status = stored status, except unpaid past-due -> OVERDUE.
PRIMARY_TABS = (
    ('all', 'All invoices', None),
    ('pending', 'Pending', Invoice.Status.PENDING),
    ('paid', 'Paid', Invoice.Status.PAID),
)
# Shown only when the customer has such invoices (or the tab is selected), so every supported
# status stays reachable without adding unused tabs.
EXTRA_TABS = (
    ('overdue', 'Overdue', Invoice.Status.OVERDUE),
    ('void', 'Void', Invoice.Status.VOID),
)
STATUS_BY_KEY = {key: status for key, _label, status in PRIMARY_TABS + EXTRA_TABS}

DUE_OPTIONS = (
    ('', 'All dates'),
    ('today', 'Due today'),
    ('next7', 'Due in the next 7 days'),
    ('month', 'Due this month'),
    ('last30', 'Due in the last 30 days'),
    ('older', 'Due more than 30 days ago'),
)
DUE_KEYS = {key for key, _label in DUE_OPTIONS if key}


def customer_invoices(user, now):
    return Invoice.objects.filter(order__customer__user=user).annotate(
        effective_status=Case(
            When(status__in=UNPAID, due_date__lt=now, then=Value(Invoice.Status.OVERDUE)),
            When(status=Invoice.Status.OVERDUE, then=Value(Invoice.Status.OVERDUE)),
            default=F('status'),
            output_field=CharField(),
        )
    )


def parse_filters(params):
    status = params.get('status', 'all')
    if status not in STATUS_BY_KEY:
        status = 'all'
    term = ' '.join(params.get('q', '').split())[:MAX_SEARCH_LENGTH]
    due = params.get('due', '')
    if due not in DUE_KEYS:
        due = ''
    return {'status': status, 'q': term, 'due': due}


def search_condition(term):
    """Match invoice number, or order number (with or without '#')."""
    condition = Q(invoice_number__icontains=term)
    number = term.lstrip('#').strip()
    if number.isascii() and number.isdigit() and len(number) <= 18:
        condition |= Q(order_id=int(number))
    return condition


def due_range(key, now):
    """Return (start, end) aware datetimes (start inclusive, end exclusive; None = open) for a due filter."""
    local = timezone.localtime(now)
    tz = local.tzinfo
    today = datetime.combine(local.date(), time.min, tzinfo=tz)
    day = timedelta(days=1)
    if key == 'today':
        return today, today + day
    if key == 'next7':
        return today, today + 7 * day
    if key == 'month':
        first = today.replace(day=1)
        following = (first + 32 * day).replace(day=1)
        return first, following
    if key == 'last30':
        return today - 30 * day, today
    if key == 'older':
        return None, today - 30 * day
    return None, None


def apply_filters(queryset, filters, now):
    status = STATUS_BY_KEY[filters['status']]
    if status:
        queryset = queryset.filter(effective_status=status)
    if filters['due']:
        start, end = due_range(filters['due'], now)
        if start is not None:
            queryset = queryset.filter(due_date__gte=start)
        if end is not None:
            queryset = queryset.filter(due_date__lt=end)
    if filters['q']:
        queryset = queryset.filter(search_condition(filters['q']))
    return queryset


def query_string(filters, *, status=None, page=None):
    status = filters['status'] if status is None else status
    items = []
    if status != 'all':
        items.append(('status', status))
    if filters['q']:
        items.append(('q', filters['q']))
    if filters['due']:
        items.append(('due', filters['due']))
    if page and page > 1:
        items.append(('page', page))
    return urlencode(items)


def listing_url(filters, **kwargs):
    query = query_string(filters, **kwargs)
    return f"{reverse('invoices')}?{query}" if query else reverse('invoices')


def build_invoices_context(user, params, now=None):
    now = now or timezone.now()
    base = customer_invoices(user, now)
    present = set(base.values_list('effective_status', flat=True).distinct())
    filters = parse_filters(params)

    records = apply_filters(base, filters, now).select_related('order').order_by('-created_at', '-pk')
    paginator = Paginator(records, PAGE_SIZE)
    page_obj = paginator.get_page(params.get('page'))

    tabs = []
    for key, label, status in PRIMARY_TABS + EXTRA_TABS:
        if (key, label, status) in EXTRA_TABS and status not in present and filters['status'] != key:
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
                page_links.append({'number': entry, 'url': listing_url(filters, page=entry),
                                   'current': entry == page_obj.number})

    return {
        'page_obj': page_obj,
        'filters': filters,
        'tabs': tabs,
        'due_options': [{'value': value, 'label': label, 'selected': value == filters['due']}
                        for value, label in DUE_OPTIONS],
        'page_links': page_links,
        'previous_url': listing_url(filters, page=page_obj.previous_page_number()) if page_obj.has_previous() else '',
        'next_url': listing_url(filters, page=page_obj.next_page_number()) if page_obj.has_next() else '',
        'total_count': paginator.count,
        'showing_start': page_obj.start_index() if paginator.count else 0,
        'showing_end': page_obj.end_index() if paginator.count else 0,
        'has_invoices': bool(present),
        'filters_active': bool(filters['q'] or filters['due'] or filters['status'] != 'all'),
        'clear_url': reverse('invoices'),
    }
