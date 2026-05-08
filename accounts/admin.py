from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AbjadUserAdmin(UserAdmin):
    list_display = (
        "username",
        "display_name",
        "first_name",
        "last_name",
        "is_staff",
        "can_access_main_table",
        "is_active",
    )
    fieldsets = UserAdmin.fieldsets + (("اطلاعات ابجد", {"fields": ("display_name", "can_access_main_table")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("اطلاعات ابجد", {"fields": ("display_name", "can_access_main_table")}),)
