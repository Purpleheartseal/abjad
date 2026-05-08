from django.contrib import admin

from .models import ChangeLog, MainEntry, ProjectEntry, TableProject


@admin.register(TableProject)
class TableProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "updated_at")
    search_fields = ("name", "description", "owner__username", "owner__display_name")
    list_filter = ("status",)
    filter_horizontal = ("members",)


@admin.register(ProjectEntry)
class ProjectEntryAdmin(admin.ModelAdmin):
    list_display = ("row_number", "project", "phrase", "abjad_value", "review_status")
    search_fields = ("phrase", "project__name")
    list_filter = ("review_status", "project")


@admin.register(MainEntry)
class MainEntryAdmin(admin.ModelAdmin):
    list_display = ("row_number", "phrase", "abjad_value", "source_project", "published_by")
    search_fields = ("phrase",)


@admin.register(ChangeLog)
class ChangeLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target_model", "target_label", "actor", "undone_at")
    list_filter = ("action", "target_model")
    search_fields = ("target_label", "actor__username", "actor__display_name")

# Register your models here.
