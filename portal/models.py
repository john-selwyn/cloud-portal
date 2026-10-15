import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property


class OrderQuerySet(models.QuerySet):
    def with_initial_invoice(self):
        return self.prefetch_related(models.Prefetch(
            "invoices", queryset=Invoice.objects.filter(purpose="INITIAL"),
            to_attr="_initial_invoices",
        ))


class VPSPlan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    cpu = models.PositiveIntegerField(help_text="Number of vCPU cores")
    ram = models.PositiveIntegerField(help_text="RAM in GB")
    storage = models.PositiveIntegerField(help_text="Storage in GB")

    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    yearly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile"
    )

    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class Order(models.Model):

    objects = OrderQuerySet.as_manager()

    @cached_property
    def invoice(self):
        """Compatibility accessor: always the original purchase invoice."""
        if hasattr(self, "_initial_invoices"):
            if self._initial_invoices:
                return self._initial_invoices[0]
            raise Invoice.DoesNotExist("Initial invoice not found.")
        return self.invoices.get(purpose=Invoice.Purpose.INITIAL)

    def refresh_from_db(self, *args, **kwargs):
        self.__dict__.pop("invoice", None)
        self.__dict__.pop("_initial_invoices", None)
        return super().refresh_from_db(*args, **kwargs)

    checkout_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    # Billing-side request tracking, not a copy of the provisioning server's VPS model.
    provisioning_status = models.CharField(max_length=30, blank=True, editable=False)
    provisioning_vps_id = models.CharField(max_length=100, blank=True, editable=False)
    provisioning_vmid = models.CharField(max_length=100, blank=True, editable=False)
    provisioning_progress = models.PositiveSmallIntegerField(default=0, editable=False)
    provisioning_step = models.CharField(max_length=255, blank=True, editable=False)
    provisioning_ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)
    provisioning_error = models.CharField(max_length=200, blank=True, editable=False)
    provisioning_payload = models.JSONField(default=dict, blank=True, editable=False)
    provisioning_lease = models.UUIDField(null=True, blank=True, editable=False)
    provisioning_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    provisioning_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    ssh_username = models.CharField(max_length=32, blank=True, default="", editable=False)
    ssh_public_key = models.TextField(blank=True, default="", editable=False)
    ssh_host = models.CharField(max_length=255, blank=True, default="", editable=False)
    ssh_port = models.PositiveIntegerField(default=22, editable=False)
    rdp_host = models.CharField(max_length=253, blank=True, default="", editable=False)
    rdp_port = models.PositiveIntegerField(default=3389, editable=False)

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        PROVISIONING = "PROVISIONING", "Provisioning"
        ACTIVE = "ACTIVE", "Active"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"

    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    class OperatingSystem(models.TextChoices):
        UBUNTU_26_04 = "Ubuntu 26.04", "Ubuntu 26.04 LTS"
        DEBIAN_13 = "Debian 13", "Debian 13"
        WINDOWS_11 = "Windows 11", "Windows 11"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="orders"
    )

    plan = models.ForeignKey(
        VPSPlan,
        on_delete=models.PROTECT,
        related_name="orders"
    )

    billing_cycle = models.CharField(
        max_length=20,
        choices=BillingCycle.choices
    )

    operating_system = models.CharField(
        max_length=50,
        choices=OperatingSystem.choices,
        default=OperatingSystem.UBUNTU_26_04,
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id}"


class Invoice(models.Model):

    class Purpose(models.TextChoices):
        INITIAL = "INITIAL", "Initial purchase"
        RENEWAL = "RENEWAL", "Renewal"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"
        OVERDUE = "OVERDUE", "Overdue"

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="invoices"
    )

    purpose = models.CharField(max_length=10, choices=Purpose.choices, default=Purpose.INITIAL)
    subscription = models.ForeignKey("Subscription", on_delete=models.PROTECT,
                                     related_name="renewal_invoices", null=True, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="PHP")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order"], condition=models.Q(purpose="INITIAL"),
                                    name="one_initial_invoice_per_order"),
            models.UniqueConstraint(fields=["subscription", "period_start"],
                                    condition=models.Q(purpose="RENEWAL"),
                                    name="one_renewal_invoice_per_period"),
            models.CheckConstraint(condition=(
                models.Q(purpose="INITIAL", subscription__isnull=True,
                         period_start__isnull=True, period_end__isnull=True)
                | models.Q(purpose="RENEWAL", subscription__isnull=False,
                           period_start__isnull=False, period_end__isnull=False,
                           period_end__gt=models.F("period_start"))), name="invoice_period_shape"),
        ]

    def clean(self):
        super().clean()
        if self.subscription_id and self.subscription.order_id != self.order_id:
            raise ValidationError("Invoice subscription must belong to the same order.")

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.status in (self.Status.PENDING, self.Status.OVERDUE) and self.due_date < timezone.now()

    invoice_number = models.CharField(
        max_length=50,
        unique=True
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    due_date = models.DateTimeField()

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invoice_number


class XenditCheckout(models.Model):
    class Status(models.TextChoices):
        CREATING = "CREATING", "Creating checkout"
        ACTIVE = "ACTIVE", "Awaiting payment"
        UNKNOWN = "UNKNOWN", "Needs reconciliation"
        VERIFYING = "VERIFYING", "Verifying payment"
        COMPLETED = "COMPLETED", "Payment confirmed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELED = "CANCELED", "Canceled"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="checkouts")
    provider = models.CharField(max_length=20, default="XENDIT", editable=False)
    reference_id = models.CharField(max_length=100, unique=True, editable=False)
    payment_session_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    payment_link_url = models.URLField(max_length=2048, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATING)
    verified_payment_id = models.CharField(max_length=100, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["order"], condition=models.Q(status__in=["CREATING", "ACTIVE", "UNKNOWN", "VERIFYING"]),
            name="one_open_xendit_checkout_per_order",
        )]


class Payment(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments"
    )

    provider = models.CharField(max_length=50)

    transaction_id = models.CharField(
        max_length=200,
        unique=True
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    raw_response = models.JSONField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id


class Subscription(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="subscriptions"
    )

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="subscription"
    )

    start_date = models.DateTimeField()
    next_billing_date = models.DateTimeField()
    # Agreement snapshot; next_billing_date remains the paid-through boundary.
    renewal_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    renewal_cycle = models.CharField(max_length=20, choices=Order.BillingCycle.choices, blank=True)
    renewal_currency = models.CharField(max_length=3, default="PHP")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Subscription #{self.id}"


class VPSPowerOperation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        RUNNING = "running", "running"
        SUCCEEDED = "succeeded", "succeeded"
        FAILED = "failed", "failed"
        UNKNOWN = "unknown", "unknown"

    class Result(models.TextChoices):
        EXECUTED = "executed", "executed"
        NOOP = "noop", "noop"

    class ObservedState(models.TextChoices):
        RUNNING = "running", "running"
        STOPPED = "stopped", "stopped"
        PAUSED = "paused", "paused"
        SUSPENDED = "suspended", "suspended"
        UNKNOWN = "unknown", "unknown"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="power_operations")
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    remote_operation_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    action = models.CharField(max_length=8, choices=[
        ("start", "start"), ("shutdown", "shutdown"), ("reboot", "reboot"),
    ])
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    result = models.CharField(max_length=8, choices=Result.choices, null=True, blank=True)
    observed_state = models.CharField(
        max_length=9, choices=ObservedState.choices, default=ObservedState.UNKNOWN
    )
    observed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    sync_attempts = models.PositiveSmallIntegerField(default=0)
    next_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "status", "updated_at"], name="billing_power_work_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status__in=["pending", "running", "unknown"]),
                name="one_unresolved_billing_power_per_order",
            ),
            models.CheckConstraint(
                condition=models.Q(action__in=["start", "shutdown", "reboot"]),
                name="billing_power_valid_action",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "running", "succeeded", "failed", "unknown"]),
                name="billing_power_valid_status",
            ),
        ]

    @property
    def unresolved(self):
        return self.status in {self.Status.PENDING, self.Status.RUNNING, self.Status.UNKNOWN}
