from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Extend Django's built-in UserAdmin fieldsets with organization instead
    # of replacing them, so username/password/permissions UI stays intact.
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Organization", {"fields": ("organization",)}),
    )
    list_display = ("username", "email", "organization", "is_staff", "is_active")
    list_filter = DjangoUserAdmin.list_filter + ("organization",)
