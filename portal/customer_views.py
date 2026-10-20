from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .account_access import CustomerAuthenticationForm, customer_required
from .customer_forms import ChangeEmailForm, CustomerPasswordResetForm
from .customer_security import (confirm_email, email_origin, prepare_email, request_allowed,
                                send_verification, verified_email)
from .models import CustomerEmail


@method_decorator(never_cache, name="dispatch")
class CustomerLoginView(auth_views.LoginView):
    authentication_form = CustomerAuthenticationForm

    def post(self, request, *args, **kwargs):
        if not request_allowed(request, "login", request.POST.get("username", "")[:254], limit=30, seconds=900):
            form = self.authentication_form(request=request)
            return self.render_to_response(self.get_context_data(form=form, login_limited=True), status=429)
        return super().post(request, *args, **kwargs)


@method_decorator(customer_required(allow_unverified=True), name="dispatch")
class CustomerPasswordChangeView(auth_views.PasswordChangeView):
    template_name = "customer_auth/password_change_form.html"
    def post(self, request, *args, **kwargs):
        if not request_allowed(request, "password-change", request.user.pk, limit=10, seconds=900):
            form = self.get_form()
            form.add_error(None, "Too many attempts. Please try again in 15 minutes.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)


@method_decorator(customer_required(allow_unverified=True), name="dispatch")
class CustomerPasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "customer_auth/password_change_done.html"


@method_decorator(never_cache, name="dispatch")
class CustomerPasswordResetView(auth_views.PasswordResetView):
    form_class = CustomerPasswordResetForm
    template_name = "customer_auth/password_reset_form.html"
    email_template_name = "customer_auth/password_reset_email.html"
    subject_template_name = "customer_auth/password_reset_subject.txt"

    def get_context_data(self, **kwargs):
        return super().get_context_data(mail_enabled=settings.CUSTOMER_EMAIL_ENABLED, **kwargs)

    def form_valid(self, form):
        if not settings.CUSTOMER_EMAIL_ENABLED:
            form.add_error(None, "Email recovery is not available yet. Please contact support.")
            return self.form_invalid(form)
        if request_allowed(self.request, "password-reset", form.cleaned_data["email"], limit=5):
            # Always use configured canonical origin; never build emailed links from Host.
            from urllib.parse import urlsplit
            origin = urlsplit(email_origin())
            form.save(domain_override=origin.netloc, use_https=True,
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      email_template_name=self.email_template_name,
                      subject_template_name=self.subject_template_name,
                      token_generator=self.token_generator)
        return redirect("password_reset_done")


@method_decorator(never_cache, name="dispatch")
class CustomerPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "customer_auth/password_reset_confirm.html"
    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        if user and user.is_active and not user.is_staff and not user.is_superuser:
            return user
        return None

    def form_valid(self, form):
        # Recheck under lock: concurrent submissions cannot consume one token twice.
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=self.user.pk)
            token = self.request.session.get(auth_views.INTERNAL_RESET_SESSION_TOKEN)
            if (not user.is_active or user.is_staff or user.is_superuser
                    or not self.token_generator.check_token(user, token)):
                self.validlink = False
                return self.render_to_response(self.get_context_data())
            form.user = user
            return super().form_valid(form)


@customer_required(allow_unverified=True)
@never_cache
@sensitive_post_parameters("current_password")
@require_http_methods(["GET", "POST"])
def change_email(request):
    form = ChangeEmailForm(request.user, request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not settings.CUSTOMER_EMAIL_ENABLED:
            form.add_error(None, "Email changes will be available after email delivery is configured.")
        elif not request_allowed(request, "change-email", request.user.pk):
            form.add_error(None, "Too many requests. Please try again in an hour.")
        elif form.is_valid():
            try:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=request.user.pk)
                    if not user.check_password(form.cleaned_data["current_password"]):
                        raise ValueError("Your password changed. Please sign in again.")
                    row = prepare_email(user, form.cleaned_data["email"])
                delivered = send_verification(row)
                messages.info(request, "Check the new inbox to confirm your email change. Your current email remains in use."
                              if delivered else "Email could not be sent. Your current email is unchanged; try again later.")
                return redirect("account")
            except (ValueError, IntegrityError):
                form.add_error("email", "This change could not be completed. Refresh and try another address.")
    return render(request, "registration/change_email.html", {
        "form": form, "mail_enabled": settings.CUSTOMER_EMAIL_ENABLED})


@customer_required(allow_unverified=True)
@require_POST
def resend_verification(request):
    if not settings.CUSTOMER_EMAIL_ENABLED:
        messages.info(request, "Email verification will be available after email delivery is configured.")
    elif not request.user.email:
        return redirect("change_email")
    elif not request_allowed(request, "verify-email", request.user.pk):
        messages.info(request, "Too many requests. Please try again in an hour.")
    elif verified_email(request.user):
        messages.info(request, "Your current email is already verified.")
    else:
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                row = prepare_email(user, user.email)
            delivered = send_verification(row)
            messages.info(request, "Check your inbox for a confirmation link." if delivered
                          else "Email could not be sent. Please try again later.")
        except (ValueError, IntegrityError):
            messages.info(request, "This email could not be verified. Please choose another address.")
    return redirect("account")


@customer_required(allow_unverified=True)
@require_POST
def cancel_email_change(request):
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        CustomerEmail.objects.filter(user=request.user, verified_at__isnull=True).delete()
    messages.info(request, "Pending email confirmation cancelled. Your current email is unchanged.")
    return redirect("account")


@never_cache
@require_http_methods(["GET", "POST"])
def verify_email(request, token):
    valid = confirm_email(token, apply=request.method == "POST")
    response = render(request, "registration/verify_email.html", {
        "validlink": valid, "confirmed": valid and request.method == "POST"})
    response["Referrer-Policy"] = "no-referrer"
    return response


@customer_required(allow_unverified=True)
@require_GET
def email_verification_needed(request):
    if verified_email(request.user):
        return redirect("dashboard")
    return render(request, "registration/email_verification_needed.html", {
        "mail_enabled": settings.CUSTOMER_EMAIL_ENABLED})
