import base64
import binascii

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from .models import Customer, Order


SSH_KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
}


def validate_ssh_public_key(value):
    value = (value or "").strip()
    if not value or len(value) > 4096 or "\n" in value or "\r" in value:
        raise forms.ValidationError("Enter one OpenSSH public key.")
    parts = value.split(None, 2)
    if len(parts) < 2 or parts[0] not in SSH_KEY_TYPES:
        raise forms.ValidationError("Enter a supported OpenSSH public key.")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        raise forms.ValidationError("The SSH public key is not valid.") from None
    if len(decoded) < 16 or len(decoded) > 2048:
        raise forms.ValidationError("The SSH public key is not valid.")
    return value


class RegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=200)
    email = forms.EmailField(max_length=254)
    company = forms.CharField(max_length=200, required=False)
    phone = forms.CharField(max_length=50, required=False)

    def clean_email(self):
        from .customer_security import email_available, normalize_email
        email = normalize_email(self.cleaned_data["email"])
        if not email_available(email):
            raise forms.ValidationError("This email address cannot be used. Choose another address or recover your account.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["full_name", "username", "email", "company", "phone", "password1", "password2"])
        for name, autocomplete in (("full_name", "name"), ("email", "email"),
                                   ("company", "organization"), ("phone", "tel")):
            self.fields[name].widget.attrs["autocomplete"] = autocomplete
        self.fields["phone"].widget.input_type = "tel"
        self.fields["email"].help_text = "Use an address you control for account recovery."


class AccountForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("full_name", "company", "phone")
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "company": forms.TextInput(attrs={"autocomplete": "organization"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "type": "tel"}),
        }


class BillingCycleForm(forms.Form):
    operating_system = forms.ChoiceField(
        label="Operating system",
        choices=Order.OperatingSystem.choices,
    )
    billing_cycle = forms.ChoiceField(choices=Order.BillingCycle.choices, widget=forms.RadioSelect)
    ssh_public_key = forms.CharField(
        label="SSH public key",
        required=False,
        max_length=4096,
        strip=True,
        validators=[validate_ssh_public_key],
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "ssh-ed25519 AAAA... your-device",
            "autocomplete": "off",
            "spellcheck": "false",
        }),
        help_text="Paste your PUBLIC key only. Never paste your private key.",
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        if not settings.WINDOWS_ORDERING_ENABLED:
            self.fields["operating_system"].choices = [
                choice for choice in Order.OperatingSystem.choices
                if choice[0] != Order.OperatingSystem.WINDOWS_11
            ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("operating_system") == Order.OperatingSystem.WINDOWS_11:
            if (self.plan is None or self.plan.cpu < 2
                    or self.plan.ram < 4 or self.plan.storage < 64):
                raise forms.ValidationError(
                    "Windows 11 requires at least 2 vCPU, 4 GB RAM, and 64 GB storage."
                )
            cleaned["ssh_public_key"] = ""
        elif cleaned.get("operating_system") and not cleaned.get("ssh_public_key"):
            self.add_error("ssh_public_key", "An SSH public key is required for Linux.")
        return cleaned
