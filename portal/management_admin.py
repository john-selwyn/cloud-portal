"""Staff operations surface; payment/provisioning state remains workflow-owned."""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.admin.models import LogEntry
from django.contrib.admin.utils import quote
from django.core.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

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
                path("monitoring/overview/", self.admin_view(self.monitoring_overview), name="monitoring_overview"),
                path("monitoring/history/", self.admin_view(self.monitoring_history), name="monitoring_history"),
                ] + super().get_urls()

    def each_context(self, request):
        context = super().each_context(request)
        context["management_ui"] = True
        context["can_view_services"] = request.user.has_perm("portal.view_order")
        context["can_manage_staff"] = request.user.is_superuser
        context["can_view_monitoring"] = request.user.is_superuser
        return context

    def monitoring_context(self, request):
        """Shared by the page and its overview fragment. Reads the saved snapshot only."""
        from .monitoring import MonitoringError, dashboard, host_configs
        from .monitoring_history import RANGES
        try:
            graph_hosts = [config["name"] for config in host_configs()]
        except MonitoringError:
            graph_hosts = []
        return {**self.each_context(request), "title": "Infrastructure monitoring", "monitor": dashboard(),
                "tz_name": settings.MONITORING_TIME_ZONE, "tz_label": settings.MONITORING_TIME_ZONE_LABEL,
                "collection_interval": settings.MONITORING_COLLECTION_INTERVAL_SECONDS // 60 or 1,
                "stale_seconds": settings.MONITORING_STALE_SECONDS, "graph_hosts": graph_hosts,
                "graph_ranges": [(key, spec["label"]) for key, spec in RANGES.items()]}

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def monitoring(self, request):
        # Infrastructure inventory is broader than ordinary billing-record access.
        if not request.user.is_superuser:
            raise PermissionDenied
        request.current_app = self.name
        return TemplateResponse(request, "management/monitoring.html", self.monitoring_context(request))

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def monitoring_overview(self, request):
        """HTML for the refreshable Overview regions. Saved snapshot only: never contacts Proxmox."""
        if not request.user.is_superuser:
            raise PermissionDenied
        request.current_app = self.name
        return TemplateResponse(request, "management/monitoring_regions.html", self.monitoring_context(request))

    @method_decorator(require_http_methods(["GET", "HEAD"]))
    def monitoring_history(self, request):
        """Cached Proxmox RRD history as JSON for the Graphs tab (read-only GETs, server-side)."""
        if not request.user.is_superuser:
            raise PermissionDenied
        from . import monitoring_history as history
        from .monitoring import dashboard, thresholds
        host, range_key = request.GET.get("host", "")[:64], request.GET.get("range", "24h")
        monitor = dashboard()
        snapshot_host = next((item for item in monitor["hosts"] if item["name"] == host), None)
        try:
            payload = history.get_history(host, range_key, snapshot_host)
        except LookupError as error:
            return JsonResponse({"error": "Unknown " + str(error) + "."}, status=400 if str(error) == "range" else 404)
        payload = {**payload, "current": history.current_values(snapshot_host),
                   "snapshot_at": monitor["observed_epoch"], "timezone": settings.MONITORING_TIME_ZONE,
                   "timezone_label": settings.MONITORING_TIME_ZONE_LABEL, "thresholds": thresholds()}
        response = JsonResponse(payload)
        response["Cache-Control"] = "private, no-store"
        return response

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
    fields = ("invoice_number", "order", "amount", "status", "due_date", "paid_at", "created_at")


class ManagedPaymentAdmin(WorkflowRecordMixin, PaymentAdmin):
    search_fields = ("transaction_id", "invoice__invoice_number")
    list_select_related = ("invoice",)
    fields = ("transaction_id", "invoice", "provider", "amount", "status", "paid_at", "created_at")


class ManagedSubscriptionAdmin(WorkflowRecordMixin, SubscriptionAdmin):
    search_fields = ("customer__full_name", "=order__id")
    list_select_related = ("customer", "order")
    fields = ("id", "customer", "order", "start_date", "next_billing_date", "status", "created_at")


for model, model_admin in [(Customer, ManagedCustomerAdmin), (VPSPlan, ManagedPlanAdmin),
                           (Order, ManagedOrderAdmin), (Invoice, ManagedInvoiceAdmin),
                           (Payment, ManagedPaymentAdmin), (Subscription, ManagedSubscriptionAdmin)]:
    management_site.register(model, model_admin)
