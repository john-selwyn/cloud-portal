from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .customer_security import email_available, normalize_email, logger


class ChangeEmailForm(forms.Form):
    email = forms.EmailField(max_length=254, label="New email address",
                            widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    current_password = forms.CharField(strip=False, widget=forms.PasswordInput(
        attrs={"autocomplete": "current-password"}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = normalize_email(self.cleaned_data["email"])
        if email == normalize_email(self.user.email):
            raise forms.ValidationError("This is already your current email. Use Verify email on your account page.")
        if not email_available(email, self.user):
            raise forms.ValidationError("This email address cannot be used. Choose another address or recover your account.")
        return email

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Your current password was incorrect.")
        return password


class CustomerPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        # Refuse ambiguity, including customer/staff collisions in historical data.
        users = list(User.objects.filter(email__iexact=normalize_email(email))[:2])
        if len(users) == 1:
            user = users[0]
            if user.is_active and not user.is_staff and not user.is_superuser and user.has_usable_password():
                yield user

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        subject = "".join(render_to_string(subject_template_name, context).splitlines())
        body = render_to_string(email_template_name, context)
        try:
            send_mail(subject, body, from_email, [to_email])
        except Exception:
            logger.warning("Customer recovery delivery failed; check mail service privately.")
