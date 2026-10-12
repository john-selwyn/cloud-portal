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
from portal.management_admin import legacy_admin_site, management_site

urlpatterns = [
    path("management/", management_site.urls),
    path("admin/", legacy_admin_site.urls),
    path("", include("portal.urls")),
    path(
        "accounts/",
        include("django.contrib.auth.urls"),
    ),
]
