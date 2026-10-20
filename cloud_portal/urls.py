"""
URL configuration for cloud_portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import include, path
from portal import customer_views
from django.contrib.auth import views as auth_views
from portal.management_admin import legacy_admin_site, management_site

urlpatterns = [
    path("management/", management_site.urls),
    path("admin/", legacy_admin_site.urls),
    path("accounts/login/", customer_views.CustomerLoginView.as_view(), name="login"),
    path("accounts/password_change/", customer_views.CustomerPasswordChangeView.as_view(), name="password_change"),
    path("accounts/password_change/done/", customer_views.CustomerPasswordChangeDoneView.as_view(), name="password_change_done"),
    path("accounts/password_reset/", customer_views.CustomerPasswordResetView.as_view(), name="password_reset"),
    path("accounts/password_reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="customer_auth/password_reset_done.html"), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", customer_views.CustomerPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("accounts/reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="customer_auth/password_reset_complete.html"), name="password_reset_complete"),
    path("accounts/email/change/", customer_views.change_email, name="change_email"),
    path("accounts/email/resend/", customer_views.resend_verification, name="resend_verification"),
    path("accounts/email/cancel/", customer_views.cancel_email_change, name="cancel_email_change"),
    path("accounts/email/verify/<str:token>/", customer_views.verify_email, name="verify_email"),
    path("accounts/email/required/", customer_views.email_verification_needed, name="email_verification_needed"),
    path("", include("portal.urls")),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
