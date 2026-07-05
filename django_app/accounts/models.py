"""
Custom user model, set as AUTH_USER_MODEL before the first migration.
Organization exists as its own table (not just a string field) because
Phase 7's BigQuery analytics scopes every query by organization_id, and
Phase 2's Document/Job models need a real FK to filter and join on.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    """
    Extends Django's built-in user with an organization FK. Everything else
    (username, email, password, is_staff, etc.) comes from AbstractUser.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
        help_text="Org this user belongs to. Used to scope documents, jobs, and analytics.",
    )

    def __str__(self) -> str:
        return self.username
