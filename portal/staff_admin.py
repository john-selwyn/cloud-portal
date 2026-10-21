"""Superuser-only staff account administration, with no customer reassignment."""
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm


class StaffCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set before the first save so the customer-profile signal skips staff.
        self.instance.is_staff = True
        self.instance.is_superuser = False


class StaffAccountAdmin(UserAdmin):
    add_form = StaffCreationForm
    add_form_template = "admin/change_form.html"
    list_display = ("username", "first_name", "last_name", "email", "is_active", "is_superuser")
    list_filter = ("is_active", "is_superuser")
    filter_horizontal = ("user_permissions",)
    add_fieldsets = (("New staff account", {"fields": (
        "username", "first_name", "last_name", "email", "password1", "password2",
    ), "description": "Creates a staff account. Assign Management permissions after saving."}),)
    fieldsets = (
        ("Staff account", {"fields": ("username", "password", "first_name", "last_name", "email", "is_active")}),
        ("Access", {"fields": ("user_permissions", "groups"),
                    "description": "Assign only the permissions needed. Existing group membership is displayed for review."}),
        ("Account information", {"fields": ("is_staff", "is_superuser", "last_login", "date_joined")}),
    )
    readonly_fields = ("username", "is_staff", "is_superuser", "groups", "last_login", "date_joined")
    actions = None

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(request, form_url, {**(extra_context or {}), "title": "Add staff account"})

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "title": "Staff accounts"})

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_staff=True)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Superuser identity/access is managed through trusted legacy tools.
        return request.user.is_superuser and (obj is None or not obj.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "user_permissions":
            # Preserve existing grants; only a superuser can access this form.
            # Default grouping keeps portal grants together in the selector.
            field.queryset = field.queryset.select_related("content_type")
        return field

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_staff = True
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
