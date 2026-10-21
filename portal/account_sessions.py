"""Route staff cookies through Django's standard session/CSRF/message middleware.

Settings stay immutable across requests. Customer cookie names remain unchanged
so existing customer sessions are preserved. Staff sign in again after rollout.
"""
from django.conf import settings


class AccountSessionBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        staff_surface = any(request.path_info == prefix or request.path_info.startswith(prefix + "/")
                            for prefix in ("/management", "/admin"))
        pairs = ((settings.SESSION_COOKIE_NAME, "management_sessionid"),
                 (settings.CSRF_COOKIE_NAME, "management_csrftoken"),
                 ("messages", "management_messages"))
        if staff_surface:
            for customer_name, staff_name in pairs:
                request.COOKIES.pop(customer_name, None)
                if staff_name in request.COOKIES:
                    request.COOKIES[customer_name] = request.COOKIES[staff_name]
        response = self.get_response(request)
        if staff_surface:
            for customer_name, staff_name in pairs:
                if customer_name in response.cookies:
                    original = response.cookies.pop(customer_name)
                    response.cookies[staff_name] = original.value
                    for key, value in original.items():
                        response.cookies[staff_name][key] = value
        return response
