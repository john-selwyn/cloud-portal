"""Separate staff authentication from customer account workflows."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError


class CustomerAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username or email"

    def clean(self):
        identifier = self.cleaned_data.get("username", "").strip()
        if "@" in identifier and not User.objects.filter(username=identifier).exists():
            matches = list(User.objects.filter(email__iexact=identifier)[:2])
            if len(matches) != 1:
                # Run a password hash to reduce obvious timing differences.
                User().set_password(self.cleaned_data.get("password", ""))
                raise self.get_invalid_login_error()
            self.cleaned_data["username"] = matches[0].username
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_staff or user.is_superuser:
            raise ValidationError("Staff accounts sign in at the Management Portal.", code="staff_account")


def customer_required(view=None, *, allow_unverified=False):
    if view is None:
        return lambda wrapped: customer_required(wrapped, allow_unverified=allow_unverified)
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            raise PermissionDenied("Use a customer account for customer services.")
        if not allow_unverified:
            from .models import Customer
            from .customer_security import verified_email
            from django.shortcuts import redirect
            if (Customer.objects.filter(user=request.user, email_verification_required=True).exists()
                    and not verified_email(request.user)):
                return redirect("email_verification_needed")
        return view(request, *args, **kwargs)
    return login_required(wrapped)
