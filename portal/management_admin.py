"""Staff operations surface; payment/provisioning state remains workflow-owned."""
from django import forms
from django.conf import settings
from django.core import signing
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.admin.models import LogEntry
from django.contrib.admin.utils import quote
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta

from . import provisioning
from .admin import CustomerAdmin, InvoiceAdmin, OrderAdmin, PaymentAdmin, SubscriptionAdmin, VPSPlanAdmin
from .models import Customer, Invoice, Order, Payment, Subscription, VPSPlan
from django.contrib.auth.models import User
from .staff_admin import StaffAccountAdmin


class ManagementSite(admin.AdminSite):
    site_header = "ICT Ventures · Management Portal"
    site_title = "ICT Ventures Management"
    index_title = "Operations overview"
    index_template = "management/index.html"
    site_url = None

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        for app in app_list:
            for model in app["models"]:
                if app["app_label"] == "auth" and model["object_name"] == "User":
                    model["name"] = "Staff accounts"
        return app_list

    def get_urls(self):
        return [path("services/", self.admin_view(self.services), name="services"),
                path("monitoring/", self.admin_view(self.monitoring), name="monitoring"),
                path("renewals/", self.admin_view(self.renewals), name="renewals"),
                path("renewals/<int:subscription_id>/invoice/", self.admin_view(self.renewal_invoice),
                     name="renewal_invoice")] + super().get_urls()

    def each_context(self, request):
        context = super().each_context(request)
        context["management_ui"] = True
        context["can_view_services"] = request.user.has_perm("portal.view_order")
        context["can_manage_staff"] = request.user.is_superuser
        context["can_view_monitoring"] = request.user.is_superuser
        context["can_view_renewals"] = request.user.has_perms(["portal.view_subscription", "portal.view_invoice"])
        return context

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def renewals(self, request):
        if not request.user.has_perms(["portal.view_subscription", "portal.view_invoice"]):
            raise PermissionDenied
        from .renewals import lead_days, review
        now = timezone.now()
        limit = now + timedelta(days=lead_days())
        records = Subscription.objects.select_related("order__plan", "customer").order_by("next_billing_date", "pk")
        status = request.GET.get("status", "")
        query = request.GET.get("q", "").strip()[:200]
        counts = {"upcoming": records.filter(status="ACTIVE", next_billing_date__gt=now,
                                             next_billing_date__lte=limit).count(),
                  "overdue": records.filter(status="ACTIVE", next_billing_date__lte=now).count(),
                  "unpaid": Invoice.objects.filter(purpose="RENEWAL", status__in=["PENDING", "OVERDUE"]).count()}
        if status == "upcoming":
            records = records.filter(status="ACTIVE", next_billing_date__gt=now, next_billing_date__lte=limit)
        elif status == "overdue":
            records = records.filter(status="ACTIVE", next_billing_date__lte=now)
        elif status == "unpaid":
            records = records.filter(renewal_invoices__status__in=["PENDING", "OVERDUE"]).distinct()
        if query:
            match = Q(customer__full_name__icontains=query)
            if query.isdecimal() and len(query) < 19:
                match |= Q(pk=int(query)) | Q(order_id=int(query))
            records = records.filter(match)
        page = Paginator(records, 30).get_page(request.GET.get("page"))
        proposals = [review(sub, now=now) for sub in page]
        request.current_app = self.name
        return TemplateResponse(request, "management/renewals.html", {
            **self.each_context(request), "title": "VPS renewals", "page": page,
            "proposals": proposals, "q": query, "status": status, "counts": counts,
            "lead_days": lead_days(), "can_issue": request.user.is_superuser,
            "generation_enabled": settings.RENEWAL_INVOICING_ENABLED,
        })

    @method_decorator(require_http_methods(["GET", "POST"]))
    def renewal_invoice(self, request, subscription_id):
        if not request.user.is_superuser:
            raise PermissionDenied
        from .renewals import agreement, generate_invoice, review
        sub = get_object_or_404(Subscription.objects.select_related("order", "customer"), pk=subscription_id)
        if request.method == "POST":
            try:
                data = signing.loads(request.POST.get("review_token", ""), salt="renewal-review", max_age=3600)
                if data.get("subscription") != sub.pk:
                    raise signing.BadSignature
                due = parse_datetime(data["due"])
                invoice, created = generate_invoice(sub.pk, actor=request.user, expected_due=due,
                                                    expected_agreement=data["agreement"])
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                messages.error(request, "This review expired or is invalid. Review the renewal again.")
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, "Renewal invoice issued." if created else "This renewal invoice already exists.")
                return HttpResponseRedirect(reverse("management:portal_invoice_change", args=[invoice.pk]))
            return HttpResponseRedirect(reverse("management:renewal_invoice", args=[sub.pk]))
        request.current_app = self.name
        return TemplateResponse(request, "management/renewal_invoice.html", {
            **self.each_context(request), "title": "Review renewal invoice", "proposal": review(sub),
            "review_token": signing.dumps({"subscription": sub.pk, "due": sub.next_billing_date.isoformat(),
                                           "agreement": agreement(sub)},
                                           salt="renewal-review"),
            "generation_enabled": settings.RENEWAL_INVOICING_ENABLED,
        })

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def monitoring(self, request):
        # Infrastructure inventory is broader than ordinary billing-record access.
        if not request.user.is_superuser:
            raise PermissionDenied
        from .monitoring import dashboard
        request.current_app = self.name
        return TemplateResponse(request, "management/monitoring.html", {
            **self.each_context(request), "title": "Infrastructure monitoring", "monitor": dashboard(),
        })

    def index(self, request, extra_context=None):
        cards = []
        for model, label in [(Customer, "Customers"), (Order, "Orders"), (VPSPlan, "Plans"),
                             (Invoice, "Invoices"), (Payment, "Payments"), (Subscription, "Subscriptions")]:
            if request.user.has_perm(f"portal.view_{model._meta.model_name}"):
                records = model.objects.all()
                if model is Customer:
                    records = records.filter(user__is_staff=False, user__is_superuser=False)
                cards.append({"label": label, "count": records.count(),
                              "url": reverse(f"management:portal_{model._meta.model_name}_changelist")})
        recent_actions = []
        for entry in LogEntry.objects.filter(user=request.user).select_related("content_type").order_by("-action_time", "-pk")[:10]:
            model = entry.content_type.model_class() if entry.content_type else None
            model_admin = self._registry.get(model)
            if not model_admin or not model_admin.has_view_or_change_permission(request):
                continue
            recent_actions.append({"entry": entry, "url": "" if entry.is_deletion() else reverse(
                f"management:{model._meta.app_label}_{model._meta.model_name}_change", args=[quote(entry.object_id)],
            )})
        return super().index(request, {**(extra_context or {}), "cards": cards, "recent_actions": recent_actions})

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def services(self, request):
        if not request.user.has_perm("portal.view_order"):
            raise PermissionDenied
        # Include failed/in-flight services, even before a subscription exists.
        orders = Order.objects.select_related("customer", "plan").filter(
            Q(status__in=[Order.Status.PROVISIONING, Order.Status.ACTIVE, Order.Status.FAILED])
            | ~Q(provisioning_vmid="") | ~Q(provisioning_vps_id="")
        ).order_by("-created_at", "-pk")
        query = request.GET.get("q", "").strip()[:200]
        status = request.GET.get("status", "")
        if query:
            match = Q(customer__full_name__icontains=query) | Q(provisioning_vmid__icontains=query)
            if query.isdecimal():
                match |= Q(pk=int(query)) if len(query) < 19 else Q(pk__isnull=True)
            orders = orders.filter(match)
        if status in Order.Status.values:
            orders = orders.filter(status=status)
        page = Paginator(orders, 30).get_page(request.GET.get("page"))
        request.current_app = self.name
        return TemplateResponse(request, "management/services.html", {
            **self.each_context(request), "title": "VPS services", "page": page,
            "q": query, "status": status, "statuses": Order.Status.choices,
        })


management_site = ManagementSite(name="management")
management_site.register(User, StaffAccountAdmin)


class LegacyAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError("Use the Management Portal for staff access.", code="invalid_login")


class LegacyAdminSite(admin.AdminSite):
    """Keep unrestricted legacy tools available only to trusted superusers."""
    login_form = LegacyAdminAuthenticationForm

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser


legacy_admin_site = LegacyAdminSite(name="admin")
for model, model_admin in admin.site._registry.items():
    legacy_admin_site.register(model, type(model_admin))


class NoDeleteMixin:
    def has_delete_permission(self, request, obj=None):
        return False


class WorkflowRecordMixin(NoDeleteMixin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj)


class ManagedCustomerAdmin(NoDeleteMixin, CustomerAdmin):
    search_fields = ("full_name", "company", "user__username", "user__email")
    list_select_related = ("user",)
    fields = ("user", "account_kind", "full_name", "company", "phone", "created_at")
    readonly_fields = ("user", "account_kind", "created_at")

    def get_queryset(self, request):
        records = super().get_queryset(request)
        if request.resolver_match and request.resolver_match.url_name == "portal_customer_changelist":
            return records.filter(user__is_staff=False, user__is_superuser=False)
        # Historical orders may still link an old staff-associated profile.
        return records

    @admin.display(description="Account type")
    def account_kind(self, obj):
        if obj.user.is_staff or obj.user.is_superuser:
            return "Historical staff-linked profile (existing records retained)"
        return "Customer"

    def has_add_permission(self, request):
        # Account registration already creates exactly one customer profile.
        return False


class PlanForm(forms.ModelForm):
    class Meta:
        model = VPSPlan
        fields = ("name", "description", "cpu", "ram", "storage", "monthly_price", "yearly_price", "is_active")

    def clean(self):
        data = super().clean()
        for name in ("cpu", "ram", "storage"):
            if name in data and data[name] < 1:
                self.add_error(name, "Resources must be at least 1.")
        for name in ("monthly_price", "yearly_price"):
            if name in data and data[name] < 0:
                self.add_error(name, "Price cannot be negative.")
        return data


class ManagedPlanAdmin(NoDeleteMixin, VPSPlanAdmin):
    form = PlanForm
    search_fields = ("name", "description")
    fields = ("name", "description", "cpu", "ram", "storage", "monthly_price", "yearly_price", "is_active")

    def get_readonly_fields(self, request, obj=None):
        # Unsent orders still read these resources from their plan at dispatch.
        return ("name", "cpu", "ram", "storage") if obj and obj.orders.exists() else ()


class ManagedOrderAdmin(WorkflowRecordMixin, OrderAdmin):
    search_fields = ("=id", "customer__full_name", "customer__user__email", "provisioning_vmid")
    list_select_related = ("customer", "plan")
    list_filter = ("status", "billing_cycle", "operating_system")
    fields = ("id", "customer", "plan", "billing_cycle", "operating_system", "amount", "status",
              "provisioning_status", "provisioning_vps_id", "provisioning_vmid", "provisioning_progress",
              "provisioning_step", "provisioning_ip_address", "provisioning_error",
              "provisioning_started_at", "provisioning_checked_at", "ssh_host", "ssh_port",
              "rdp_host", "rdp_port", "created_at", "updated_at")
    change_form_template = "management/order.html"

    def get_urls(self):
        return [path("<int:object_id>/sync/", self.admin_site.admin_view(self.sync),
                     name="portal_order_sync")] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, {
            **(extra_context or {}), "can_sync": request.user.has_perms(["portal.view_order", "portal.change_order"]),
        })

    @method_decorator(require_http_methods(["GET", "POST"]))
    def sync(self, request, object_id):
        if not request.user.has_perms(["portal.view_order", "portal.change_order"]):
            raise PermissionDenied
        order = get_object_or_404(Order, pk=object_id)
        if request.method == "POST":
            try:
                result = provisioning.get_vps_provisioning_status(order)
            except ValidationError as exc:
                self.message_user(request, " ".join(exc.messages), messages.ERROR)
            else:
                self.log_change(request, result, "Requested provisioning status reconciliation (no provisioning POST).")
                if result.provisioning_error:
                    self.message_user(request, "Status reconciliation reported an error. Review the order before further action.", messages.WARNING)
                else:
                    self.message_user(request, "Status reconciliation completed. Existing lease and polling limits may defer a refresh.")
            return HttpResponseRedirect(reverse("management:portal_order_change", args=[order.pk]))
        request.current_app = self.admin_site.name
        return TemplateResponse(request, "management/sync.html", {
            **self.admin_site.each_context(request), "title": f"Reconcile order #{order.pk}", "order": order,
        })


class ManagedInvoiceAdmin(WorkflowRecordMixin, InvoiceAdmin):
    search_fields = ("invoice_number", "order__customer__full_name")
    list_select_related = ("order",)
    list_display = ("invoice_number", "purpose", "order", "amount", "currency", "status", "due_date", "paid_at")
    list_filter = ("purpose", "status")
    fields = ("invoice_number", "purpose", "order", "subscription", "period_start", "period_end",
              "amount", "currency", "status", "due_date", "paid_at", "created_at")


class ManagedPaymentAdmin(WorkflowRecordMixin, PaymentAdmin):
    search_fields = ("transaction_id", "invoice__invoice_number")
    list_select_related = ("invoice",)
    fields = ("transaction_id", "invoice", "provider", "amount", "status", "paid_at", "created_at")


class ManagedSubscriptionAdmin(WorkflowRecordMixin, SubscriptionAdmin):
    search_fields = ("customer__full_name", "=order__id")
    list_select_related = ("customer", "order")
    fields = ("id", "customer", "order", "start_date", "next_billing_date", "renewal_amount",
              "renewal_cycle", "renewal_currency", "status", "created_at")


for model, model_admin in [(Customer, ManagedCustomerAdmin), (VPSPlan, ManagedPlanAdmin),
                           (Order, ManagedOrderAdmin), (Invoice, ManagedInvoiceAdmin),
                           (Payment, ManagedPaymentAdmin), (Subscription, ManagedSubscriptionAdmin)]:
    management_site.register(model, model_admin)
