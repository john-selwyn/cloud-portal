"""Separate staff authentication from customer account workflows."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied, ValidationError


class CustomerAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_staff or user.is_superuser:
            raise ValidationError("Staff accounts sign in at the Management Portal.", code="staff_account")


def customer_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            raise PermissionDenied("Use a customer account for customer services.")
        return view(request, *args, **kwargs)
    return login_required(wrapped)
