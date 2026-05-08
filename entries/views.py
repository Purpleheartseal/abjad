from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models, transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.forms import UserCreateForm, UserUpdateForm
from accounts.models import User

from .forms import (
    ImportFileForm,
    MainEntryEditForm,
    PhraseForm,
    ProjectEntryEditForm,
    TableProjectForm,
    UserProjectForm,
)
from .models import ChangeLog, MainEntry, ProjectEntry, TableProject
from .services import (
    EXPORT_HEADERS,
    SORTABLE_COLUMNS,
    build_csv_content,
    build_duplicate_groups,
    build_excel_workbook,
    calculate_phrase,
    export_sql_dump,
    export_sqlite_bytes,
    find_invalid_phrase_chars,
    import_sql_dump,
    import_sqlite_file,
    next_row_number,
    read_phrases_from_upload,
)

INLINE_EDITABLE_FIELDS = {
    "row_number",
    "phrase",
    "abjad_value",
    "prime_index",
    "digit_root",
    "abjad_sum",
    "parity_label",
    "parity_order",
    "letter_count",
    "dot_count",
    "pronounced_value",
    "alif_count",
    "abjad_saghir",
    "breakdown",
}
CALCULATED_COMPARISON_FIELDS = (
    "abjad_value",
    "prime_index",
    "digit_root",
    "abjad_sum",
    "parity_label",
    "parity_order",
    "letter_count",
    "dot_count",
    "unique_letter_count",
    "used_letters",
    "pronounced_value",
    "alif_count",
    "abjad_saghir",
    "breakdown",
)
FILTER_FIELD_DEFINITIONS = [
    ("phrase", "عبارت", "text"),
    ("abjad_value", "عدد ابجد", "number"),
    ("prime_index", "چندمین عدد اول", "number"),
    ("digit_root", "ریشه عدد", "number"),
    ("abjad_sum", "مجموع عدد ابجد", "number"),
    ("parity_label", "زوج یا فرد", "text"),
    ("parity_order", "چندمین زوج فرد", "number"),
    ("letter_count", "تعداد حروف", "number"),
    ("dot_count", "تعداد نقطه", "number"),
    ("unique_letter_count", "تعداد حروف یکتا", "number"),
    ("used_letters", "حروف استفاده شده", "text"),
    ("pronounced_value", "عدد ملفوظی", "number"),
    ("alif_count", "تعداد الف", "number"),
    ("abjad_saghir", "ابجد صغیر", "number"),
    ("breakdown", "تبدیل حرف به عدد", "text"),
]
FILTER_OPERATORS = [
    ("contains", "شامل"),
    ("exact", "دقیقا برابر"),
    ("gt", "بزرگ‌تر از"),
    ("gte", "بزرگ‌تر یا مساوی"),
    ("lt", "کمتر از"),
    ("lte", "کمتر یا مساوی"),
]
ENTRY_SNAPSHOT_FIELDS = (
    "phrase",
    "normalized_phrase",
    "abjad_value",
    "prime_index",
    "digit_root",
    "abjad_sum",
    "parity_label",
    "parity_order",
    "letter_count",
    "dot_count",
    "unique_letter_count",
    "used_letters",
    "pronounced_value",
    "alif_count",
    "abjad_saghir",
    "breakdown",
)


def staff_required(view):
    return user_passes_test(lambda user: user.is_staff)(view)


def user_can_access_main_table(user) -> bool:
    return bool(user.is_authenticated and user.can_view_main_table)


def trim_change_logs(limit: int = 100) -> None:
    stale_ids = list(ChangeLog.objects.order_by("-created_at", "-id").values_list("id", flat=True)[limit:])
    if stale_ids:
        ChangeLog.objects.filter(id__in=stale_ids).delete()


def record_change(actor, action: str, target_model: str, target_label: str, before: dict | None = None, after: dict | None = None, target_pk: int | None = None) -> None:
    ChangeLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_model=target_model,
        target_pk=target_pk,
        target_label=target_label[:255],
        snapshot_before=before or {},
        snapshot_after=after or {},
    )
    trim_change_logs()


def serialize_project_entry_snapshot(entry: ProjectEntry) -> dict:
    data = {field: getattr(entry, field) for field in ENTRY_SNAPSHOT_FIELDS}
    data.update(
        {
            "pk": entry.pk,
            "project_id": entry.project_id,
            "row_number": entry.row_number,
            "created_by_id": entry.created_by_id,
            "review_status": entry.review_status,
            "review_note": entry.review_note,
            "reviewed_by_id": entry.reviewed_by_id,
            "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else "",
            "linked_main_entry_id": getattr(getattr(entry, "main_entry", None), "pk", None),
        }
    )
    return data


def serialize_main_entry_snapshot(entry: MainEntry) -> dict:
    data = {field: getattr(entry, field) for field in ENTRY_SNAPSHOT_FIELDS}
    data.update(
        {
            "pk": entry.pk,
            "row_number": entry.row_number,
            "source_project_id": entry.source_project_id,
            "source_entry_id": entry.source_entry_id,
            "published_by_id": entry.published_by_id,
        }
    )
    return data


def serialize_project_snapshot(project: TableProject, include_entries: bool = True) -> dict:
    data = {
        "pk": project.pk,
        "name": project.name,
        "description": project.description,
        "owner_id": project.owner_id,
        "member_ids": list(project.members.values_list("pk", flat=True)),
        "status": project.status,
    }
    if include_entries:
        data["entries"] = [serialize_project_entry_snapshot(entry) for entry in project.entries.order_by("row_number", "pk")]
    return data


def serialize_user_snapshot(user: User) -> dict:
    return {
        "pk": user.pk,
        "username": user.username,
        "password": user.password,
        "display_name": user.display_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "can_access_main_table": user.can_access_main_table,
        "assigned_project_ids": list(user.assigned_projects.values_list("pk", flat=True)),
    }


def shift_main_rows(start_row: int, exclude_pk: int | None = None) -> None:
    entries = MainEntry.objects.filter(row_number__gte=start_row).exclude(pk=exclude_pk).order_by("-row_number", "-pk")
    for entry in entries:
        entry.row_number += 1
        entry.save(update_fields=["row_number", "updated_at"])


def shift_project_rows(project: TableProject, start_row: int, exclude_pk: int | None = None) -> None:
    entries = project.entries.filter(row_number__gte=start_row).exclude(pk=exclude_pk).order_by("-row_number", "-pk")
    for entry in entries:
        entry.row_number += 1
        entry.save(update_fields=["row_number", "updated_at"])


def parse_iso_datetime(value: str):
    if not value:
        return None
    return timezone.datetime.fromisoformat(value)


def restore_project_entry_snapshot(snapshot: dict) -> ProjectEntry:
    project = get_object_or_404(TableProject, pk=snapshot["project_id"])
    entry = ProjectEntry.objects.filter(pk=snapshot["pk"]).first()
    if entry is None:
        shift_project_rows(project, snapshot["row_number"])
        entry = ProjectEntry(pk=snapshot["pk"], project=project)
    for field in ENTRY_SNAPSHOT_FIELDS:
        setattr(entry, field, snapshot[field])
    entry.project = project
    entry.row_number = snapshot["row_number"]
    created_by_id = snapshot.get("created_by_id")
    reviewed_by_id = snapshot.get("reviewed_by_id")
    entry.created_by_id = created_by_id if created_by_id and User.objects.filter(pk=created_by_id).exists() else None
    entry.review_status = snapshot.get("review_status", ProjectEntry.ReviewStatus.DRAFT)
    entry.review_note = snapshot.get("review_note", "")
    entry.reviewed_by_id = reviewed_by_id if reviewed_by_id and User.objects.filter(pk=reviewed_by_id).exists() else None
    entry.reviewed_at = parse_iso_datetime(snapshot.get("reviewed_at", ""))
    entry.save()
    linked_main_entry_id = snapshot.get("linked_main_entry_id")
    if linked_main_entry_id:
        MainEntry.objects.filter(pk=linked_main_entry_id).update(source_entry=entry, source_project=project)
        sync_main_entry_from_project_entry(entry)
    resequence_project_entries(project)
    return entry


def restore_main_entry_snapshot(snapshot: dict) -> MainEntry:
    entry = MainEntry.objects.filter(pk=snapshot["pk"]).first()
    if entry is None:
        shift_main_rows(snapshot["row_number"])
        entry = MainEntry(pk=snapshot["pk"])
    for field in ENTRY_SNAPSHOT_FIELDS:
        setattr(entry, field, snapshot[field])
    entry.row_number = snapshot["row_number"]
    source_project_id = snapshot.get("source_project_id")
    source_entry_id = snapshot.get("source_entry_id")
    published_by_id = snapshot.get("published_by_id")
    entry.source_project_id = source_project_id if source_project_id and TableProject.objects.filter(pk=source_project_id).exists() else None
    entry.source_entry_id = source_entry_id if source_entry_id and ProjectEntry.objects.filter(pk=source_entry_id).exists() else None
    entry.published_by_id = published_by_id if published_by_id and User.objects.filter(pk=published_by_id).exists() else None
    entry.save()
    resequence_main_entries()
    return entry


def restore_project_snapshot(snapshot: dict) -> TableProject:
    project = TableProject.objects.filter(pk=snapshot["pk"]).first()
    if project is None:
        project = TableProject(pk=snapshot["pk"])
    project.name = snapshot["name"]
    project.description = snapshot.get("description", "")
    owner_id = snapshot["owner_id"]
    if not User.objects.filter(pk=owner_id).exists():
        raise ValueError("مالک جدول دیگر در سیستم وجود ندارد.")
    project.owner_id = owner_id
    project.status = snapshot.get("status", TableProject.Status.ACTIVE)
    project.save()
    if snapshot.get("member_ids"):
        project.members.set(User.objects.filter(pk__in=snapshot["member_ids"]))
    else:
        project.members.clear()
    for entry_snapshot in snapshot.get("entries", []):
        restore_project_entry_snapshot(entry_snapshot)
    resequence_project_entries(project)
    return project


def restore_user_snapshot(snapshot: dict) -> User:
    user = User.objects.filter(pk=snapshot["pk"]).first()
    if user is None:
        user = User(pk=snapshot["pk"])
    for field in ("username", "password", "display_name", "first_name", "last_name", "email"):
        setattr(user, field, snapshot.get(field, ""))
    user.is_staff = snapshot.get("is_staff", False)
    user.is_superuser = snapshot.get("is_superuser", False)
    user.is_active = snapshot.get("is_active", True)
    user.can_access_main_table = snapshot.get("can_access_main_table", False)
    user.save()
    if snapshot.get("assigned_project_ids"):
        user.assigned_projects.set(TableProject.objects.filter(pk__in=snapshot["assigned_project_ids"]))
    else:
        user.assigned_projects.clear()
    return user


def get_recent_change_logs(user):
    queryset = ChangeLog.objects.select_related("actor", "undone_by")
    if user.is_staff:
        return queryset
    return queryset.filter(actor=user)


def build_full_backup_payload() -> dict:
    return {
        "generated_at": timezone.now().isoformat(),
        "users": [
            serialize_user_snapshot(user)
            for user in User.objects.order_by("id")
        ],
        "projects": [
            serialize_project_snapshot(project, include_entries=False)
            for project in TableProject.objects.order_by("id")
        ],
        "project_entries": [
            serialize_project_entry_snapshot(entry)
            for entry in ProjectEntry.objects.order_by("id")
        ],
        "main_entries": [
            serialize_main_entry_snapshot(entry)
            for entry in MainEntry.objects.order_by("id")
        ],
    }


def get_accessible_projects(user):
    if user.is_staff:
        return TableProject.objects.all()
    return TableProject.objects.filter(Q(owner=user) | Q(members=user)).distinct()


def get_project_for_user(user, pk: int) -> TableProject:
    project = get_object_or_404(TableProject.objects.prefetch_related("members", "entries"), pk=pk)
    if not project.user_can_access(user):
        raise Http404("شما به این جدول دسترسی ندارید.")
    return project


def get_filter_rows(request, data=None):
    params = data or request.GET
    rows = []
    for index in range(1, 4):
        rows.append(
            {
                "index": index,
                "join": params.get(f"filter_join_{index}", "and"),
                "field": params.get(f"filter_field_{index}", ""),
                "operator": params.get(f"filter_operator_{index}", "contains"),
                "value": params.get(f"filter_value_{index}", "").strip(),
            }
        )
    return rows


def apply_filter_rows(queryset, rows):
    field_kinds = {name: kind for name, _, kind in FILTER_FIELD_DEFINITIONS}
    combined_q = None
    for row in rows:
        field = row["field"]
        operator = row["operator"]
        value = row["value"]
        if not field or not value or field not in field_kinds:
            continue
        kind = field_kinds[field]
        condition = None
        if kind == "text":
            if operator == "contains":
                condition = Q(**{f"{field}__icontains": value})
            elif operator == "exact":
                condition = Q(**{field: value})
        else:
            try:
                numeric_value = int(value)
            except ValueError:
                continue
            if operator == "exact":
                condition = Q(**{field: numeric_value})
            elif operator == "gt":
                condition = Q(**{f"{field}__gt": numeric_value})
            elif operator == "gte":
                condition = Q(**{f"{field}__gte": numeric_value})
            elif operator == "lt":
                condition = Q(**{f"{field}__lt": numeric_value})
            elif operator == "lte":
                condition = Q(**{f"{field}__lte": numeric_value})
        if condition is None:
            continue
        if combined_q is None:
            combined_q = condition
        elif row["join"] == "or":
            combined_q = combined_q | condition
        else:
            combined_q = combined_q & condition
    if combined_q is not None:
        queryset = queryset.filter(combined_q)
    return queryset


def get_table_queryset(request, queryset, data=None):
    params = data or request.GET
    filter_rows = get_filter_rows(request, params)
    q = params.get("q", "").strip()
    sort = params.get("sort", "row_number")
    direction = params.get("direction", "asc")
    if q:
        queryset = queryset.filter(phrase__icontains=q)
    queryset = apply_filter_rows(queryset, filter_rows)
    if sort not in SORTABLE_COLUMNS:
        sort = "row_number"
    order_by = f"-{sort}" if direction == "desc" else sort
    queryset = queryset.order_by(order_by, "id")
    return queryset, q, sort, direction


def paginate_queryset(request, queryset, per_page: int = 100):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def get_bulk_entries(request, queryset):
    if request.POST.get("select_all_filtered") == "1":
        filtered_queryset, _, _, _ = get_table_queryset(request, queryset, data=request.POST)
        return list(filtered_queryset)
    selected_ids = [int(value) for value in request.POST.getlist("entry_ids") if value.isdigit()]
    return list(queryset.filter(pk__in=selected_ids))


def build_project_entry(project: TableProject, user, phrase: str, row_number: int | None = None) -> ProjectEntry:
    result = calculate_phrase(phrase)
    return ProjectEntry(
        project=project,
        created_by=user,
        row_number=row_number or next_row_number(project.entries),
        **result.as_model_data(),
    )


def build_main_entry(user, phrase: str, row_number: int | None = None, source_project=None, source_entry=None) -> MainEntry:
    result = calculate_phrase(phrase)
    return MainEntry(
        row_number=row_number or next_row_number(MainEntry.objects),
        published_by=user,
        source_project=source_project,
        source_entry=source_entry,
        **result.as_model_data(),
    )


def serialize_project_entry(entry: ProjectEntry) -> dict:
    return {
        "row_number": entry.row_number,
        "phrase": entry.phrase,
        "abjad_value": entry.abjad_value,
        "prime_index": entry.prime_index,
        "digit_root": entry.digit_root,
        "abjad_sum": entry.abjad_sum,
        "parity_label": entry.parity_label,
        "parity_order": entry.parity_order,
        "letter_count": entry.letter_count,
        "dot_count": entry.dot_count,
        "unique_letter_count": entry.unique_letter_count,
        "used_letters": entry.used_letters,
        "pronounced_value": entry.pronounced_value,
        "alif_count": entry.alif_count,
        "abjad_saghir": entry.abjad_saghir,
        "breakdown": entry.breakdown,
        "review_status_display": entry.get_review_status_display(),
        "has_mismatch": getattr(entry, "has_mismatch", False),
        "mismatch_fields": getattr(entry, "mismatch_fields", []),
    }


def serialize_main_entry(entry: MainEntry) -> dict:
    return {
        "row_number": entry.row_number,
        "phrase": entry.phrase,
        "abjad_value": entry.abjad_value,
        "prime_index": entry.prime_index,
        "digit_root": entry.digit_root,
        "abjad_sum": entry.abjad_sum,
        "parity_label": entry.parity_label,
        "parity_order": entry.parity_order,
        "letter_count": entry.letter_count,
        "dot_count": entry.dot_count,
        "unique_letter_count": entry.unique_letter_count,
        "used_letters": entry.used_letters,
        "pronounced_value": entry.pronounced_value,
        "alif_count": entry.alif_count,
        "abjad_saghir": entry.abjad_saghir,
        "breakdown": entry.breakdown,
        "has_mismatch": getattr(entry, "has_mismatch", False),
        "mismatch_fields": getattr(entry, "mismatch_fields", []),
    }


def cast_inline_value(model, field_name: str, raw_value: str):
    field = model._meta.get_field(field_name)
    value = raw_value.strip()
    if isinstance(field, (models.PositiveIntegerField, models.PositiveSmallIntegerField, models.PositiveBigIntegerField, models.IntegerField)):
        return int(value)
    return value


def sync_main_entry_from_project_entry(project_entry: ProjectEntry):
    if not hasattr(project_entry, "main_entry"):
        return
    main_entry = project_entry.main_entry
    for field in (
        "phrase",
        "normalized_phrase",
        "abjad_value",
        "prime_index",
        "digit_root",
        "abjad_sum",
        "parity_label",
        "parity_order",
        "letter_count",
        "dot_count",
        "unique_letter_count",
        "used_letters",
        "pronounced_value",
        "alif_count",
        "abjad_saghir",
        "breakdown",
    ):
        setattr(main_entry, field, getattr(project_entry, field))
    main_entry.save()


def resequence_project_entries(project: TableProject):
    entries = list(project.entries.order_by("row_number", "pk"))
    for index, entry in enumerate(entries, start=1):
        if entry.row_number != index:
            entry.row_number = index
            entry.save(update_fields=["row_number", "updated_at"])


def resequence_main_entries():
    entries = list(MainEntry.objects.order_by("row_number", "pk"))
    for index, entry in enumerate(entries, start=1):
        if entry.row_number != index:
            entry.row_number = index
            entry.save(update_fields=["row_number", "updated_at"])


def detect_entry_mismatch(entry) -> tuple[bool, list[str]]:
    recalculated = calculate_phrase(entry.phrase).as_model_data()
    mismatched = [field for field in CALCULATED_COMPARISON_FIELDS if getattr(entry, field) != recalculated[field]]
    invalid_chars = find_invalid_phrase_chars(entry.phrase)
    entry.invalid_phrase_chars = invalid_chars
    if invalid_chars and "phrase" not in mismatched:
        mismatched.append("phrase")
    return bool(mismatched), mismatched


def annotate_entry_mismatches(entries):
    for entry in entries:
        entry.has_mismatch, entry.mismatch_fields = detect_entry_mismatch(entry)
    return entries


@login_required
def dashboard(request):
    projects = get_accessible_projects(request.user)
    can_access_main = user_can_access_main_table(request.user)
    stats = {
        "project_count": projects.count(),
        "project_entry_count": ProjectEntry.objects.filter(project__in=projects).count(),
        "main_entry_count": MainEntry.objects.count() if can_access_main else None,
        "pending_review_count": ProjectEntry.objects.filter(review_status=ProjectEntry.ReviewStatus.DRAFT).count()
        if request.user.is_staff
        else ProjectEntry.objects.filter(project__in=projects, review_status=ProjectEntry.ReviewStatus.DRAFT).count(),
    }
    recent_projects = projects.select_related("owner").annotate(entry_total=Count("entries"))[:6]
    recent_main_entries = MainEntry.objects.order_by("-created_at")[:10] if can_access_main else []
    return render(
        request,
        "entries/dashboard.html",
        {
            "stats": stats,
            "recent_projects": recent_projects,
            "recent_main_entries": recent_main_entries,
            "can_access_main_table": can_access_main,
        },
    )


@login_required
def project_list(request):
    projects = get_accessible_projects(request.user).select_related("owner").annotate(entry_total=Count("entries"))
    q = request.GET.get("q", "").strip()
    if q:
        projects = projects.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(request, "entries/project_list.html", {"projects": projects, "q": q})


@login_required
def project_create(request):
    form_class = TableProjectForm if request.user.is_staff else UserProjectForm
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            if not request.user.is_staff:
                project.owner = request.user
                project.status = TableProject.Status.ACTIVE
            project.save()
            if request.user.is_staff:
                form.save_m2m()
            messages.success(request, "جدول جدید با موفقیت ایجاد شد.")
            return redirect("entries:project_detail", pk=project.pk)
    else:
        form = form_class(initial={"owner": request.user.pk} if request.user.is_staff else None)
    return render(request, "entries/project_form.html", {"form": form, "title": "ایجاد جدول جدید"})


@login_required
def project_update(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if not request.user.is_staff and project.owner != request.user:
        raise Http404("فقط مالک یا مدیر می تواند این جدول را ویرایش کند.")
    form_class = TableProjectForm if request.user.is_staff else UserProjectForm
    if request.method == "POST":
        before = serialize_project_snapshot(project, include_entries=False)
        form = form_class(request.POST, instance=project)
        if form.is_valid():
            form.save()
            record_change(
                request.user,
                ChangeLog.Action.UPDATE,
                ChangeLog.TargetModel.TABLE_PROJECT,
                project.name,
                before=before,
                after=serialize_project_snapshot(project, include_entries=False),
                target_pk=project.pk,
            )
            messages.success(request, "جدول با موفقیت ویرایش شد.")
            return redirect("entries:project_detail", pk=project.pk)
    else:
        form = form_class(instance=project)
    return render(request, "entries/project_form.html", {"form": form, "title": f"ویرایش {project.name}"})


@login_required
def project_delete(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if request.method != "POST":
        raise Http404
    if not request.user.is_staff and project.owner != request.user:
        raise Http404("فقط مالک یا مدیر می تواند این جدول را حذف کند.")
    snapshot = serialize_project_snapshot(project, include_entries=True)
    project_name = project.name
    project.delete()
    record_change(
        request.user,
        ChangeLog.Action.DELETE,
        ChangeLog.TargetModel.TABLE_PROJECT,
        project_name,
        before=snapshot,
        target_pk=snapshot["pk"],
    )
    messages.success(request, f"جدول «{project_name}» حذف شد.")
    return redirect("entries:project_list")


@login_required
def project_detail(request, pk: int):
    project = get_project_for_user(request.user, pk)
    entries, q, sort, direction = get_table_queryset(
        request,
        project.entries.select_related("created_by", "reviewed_by"),
    )
    page_obj = paginate_queryset(request, entries)
    annotate_entry_mismatches(page_obj.object_list)
    return render(
        request,
        "entries/project_detail.html",
        {
            "project": project,
            "page_obj": page_obj,
            "q": q,
            "sort": sort,
            "direction": direction,
            "headers": EXPORT_HEADERS,
            "phrase_form": PhraseForm(),
            "import_form": ImportFileForm(),
            "features_project_id": project.pk,
            "move_targets": get_accessible_projects(request.user).exclude(pk=project.pk).order_by("name"),
            "filter_rows": get_filter_rows(request),
            "filter_fields": FILTER_FIELD_DEFINITIONS,
            "filter_operators": FILTER_OPERATORS,
        },
    )


@login_required
def project_calculate(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if request.method != "POST":
        raise Http404
    form = PhraseForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    result = calculate_phrase(form.cleaned_data["phrase"])
    return JsonResponse({"ok": True, "project": project.name, "result": result.as_model_data()})


@login_required
def project_add_entry(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if request.method != "POST":
        raise Http404
    form = PhraseForm(request.POST)
    if not form.is_valid():
        messages.error(request, "عبارت معتبر نیست.")
        return redirect("entries:project_detail", pk=project.pk)
    entry = build_project_entry(project, request.user, form.cleaned_data["phrase"])
    entry.save()
    messages.success(request, "رکورد جدید به جدول اضافه شد.")
    return redirect("entries:project_detail", pk=project.pk)


@login_required
def project_bulk_action(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if request.method != "POST":
        raise Http404
    action = request.POST.get("bulk_action", "").strip()
    entries = get_bulk_entries(request, project.entries.order_by("row_number", "pk"))
    if not entries:
        messages.warning(request, "هیچ عبارتی انتخاب نشده است.")
        return redirect("entries:project_detail", pk=project.pk)
    selected_ids = [entry.pk for entry in entries]
    if action == "delete":
        snapshots = [serialize_project_entry_snapshot(entry) for entry in entries]
        deleted_count, _ = project.entries.filter(pk__in=selected_ids).delete()
        for snapshot in snapshots:
            record_change(
                request.user,
                ChangeLog.Action.DELETE,
                ChangeLog.TargetModel.PROJECT_ENTRY,
                snapshot["phrase"],
                before=snapshot,
                target_pk=snapshot["pk"],
            )
        resequence_project_entries(project)
        messages.success(request, f"{deleted_count} رکورد حذف شد.")
        return redirect("entries:project_detail", pk=project.pk)
    if action == "move":
        target_id = int(request.POST.get("target_project", "0") or 0)
        if not target_id:
            messages.warning(request, "برای انتقال، پروژه مقصد را انتخاب کنید.")
            return redirect("entries:project_detail", pk=project.pk)
        target_project = get_project_for_user(request.user, target_id)
        if target_project.pk == project.pk:
            messages.warning(request, "پروژه مقصد باید با پروژه فعلی متفاوت باشد.")
            return redirect("entries:project_detail", pk=project.pk)
        start_row = next_row_number(target_project.entries)
        with transaction.atomic():
            for index, entry in enumerate(entries):
                entry.project = target_project
                entry.row_number = start_row + index
                entry.save(update_fields=["project", "row_number", "updated_at"])
                if hasattr(entry, "main_entry"):
                    entry.main_entry.source_project = target_project
                    entry.main_entry.save(update_fields=["source_project"])
            resequence_project_entries(project)
            resequence_project_entries(target_project)
        messages.success(request, f"{len(entries)} رکورد به جدول «{target_project.name}» منتقل شد.")
        return redirect("entries:project_detail", pk=project.pk)
    messages.warning(request, "عملیات گروهی انتخاب نشده است.")
    return redirect("entries:project_detail", pk=project.pk)


def get_duplicate_source_queryset(user, source_type: str, project_id: str):
    if source_type == "main":
        if not user.is_staff:
            return MainEntry.objects.none(), "شما به جدول اصلی دسترسی ندارید", None
        return MainEntry.objects.all(), "جدول اصلی", None
    accessible_projects = get_accessible_projects(user)
    project = None
    if project_id:
        project = get_object_or_404(accessible_projects, pk=project_id)
    else:
        project = accessible_projects.order_by("name").first()
    if not project:
        return ProjectEntry.objects.none(), "پروژه‌ای انتخاب نشده است", None
    return project.entries.all(), f"جدول {project.name}", project


@login_required
def features(request):
    accessible_projects = get_accessible_projects(request.user).order_by("name")
    can_access_main = user_can_access_main_table(request.user)
    can_manage_main_duplicates = request.user.is_staff
    source_type = request.GET.get("source_type", "project")
    if source_type == "main" and not can_manage_main_duplicates:
        source_type = "project"
    project_id = request.GET.get("project")
    duplicate_groups = []
    duplicate_label = ""
    selected_project = None
    calculator_phrase = request.GET.get("calculator_phrase", "").strip()
    calculator_result = None
    calculator_errors: list[str] = []
    if calculator_phrase:
        invalid = find_invalid_phrase_chars(calculator_phrase)
        if invalid:
            calculator_errors.append(f"کاراکترهای نامعتبر: {' '.join(invalid)}")
        else:
            calculator_result = calculate_phrase(calculator_phrase).as_model_data()
    if source_type in {"project", "main"}:
        queryset, duplicate_label, selected_project = get_duplicate_source_queryset(request.user, source_type, project_id)
        duplicate_groups = build_duplicate_groups(queryset)
    context = {
        "accessible_projects": accessible_projects,
        "duplicate_groups": duplicate_groups,
        "duplicate_label": duplicate_label,
        "source_type": source_type,
        "selected_project": selected_project,
        "features_project_id": project_id or "",
        "can_access_main_table": can_access_main,
        "can_manage_main_duplicates": can_manage_main_duplicates,
        "change_logs": get_recent_change_logs(request.user)[:100],
        "calculator_phrase": calculator_phrase,
        "calculator_result": calculator_result,
        "calculator_errors": calculator_errors,
    }
    return render(request, "entries/features.html", context)


@login_required
def features_duplicates_delete(request):
    if request.method != "POST":
        raise Http404
    source_type = request.POST.get("source_type", "project")
    if source_type == "main" and not request.user.is_staff:
        raise Http404("شما به جدول اصلی دسترسی ندارید.")
    project_id = request.POST.get("project", "")
    queryset, _, project = get_duplicate_source_queryset(request.user, source_type, project_id)
    groups = build_duplicate_groups(queryset)
    selected_ids = {int(value) for value in request.POST.getlist("delete_ids") if value.isdigit()}
    delete_all = request.POST.get("delete_all") == "1"
    ids_to_delete: set[int] = set()
    if delete_all:
        for group in groups:
            ids_to_delete.update(entry.pk for entry in group["entries"][1:])
    else:
        ids_to_delete = selected_ids
    if source_type == "main":
        deleted_count, _ = MainEntry.objects.filter(pk__in=ids_to_delete).delete()
    else:
        deleted_count, _ = ProjectEntry.objects.filter(pk__in=ids_to_delete, project=project).delete()
    messages.success(request, f"{deleted_count} عبارت تکراری حذف شد.")
    query = f"?source_type={source_type}"
    if project_id:
        query += f"&project={project_id}"
    return redirect(f"{reverse('entries:features')}{query}")


@staff_required
def features_database_export(request, file_format: str):
    if file_format == "sqlite":
        content = export_sqlite_bytes()
        response = HttpResponse(content, content_type="application/x-sqlite3")
        response["Content-Disposition"] = 'attachment; filename="abjad-backup.sqlite3"'
        return response
    if file_format == "sql":
        content = export_sql_dump()
        response = HttpResponse(content, content_type="application/sql; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="abjad-backup.sql"'
        return response
    raise Http404


@staff_required
def features_database_import(request):
    if request.method != "POST":
        raise Http404
    uploaded = request.FILES.get("file")
    if not uploaded:
        messages.error(request, "فایلی برای بازیابی انتخاب نشده است.")
        return redirect("entries:features")
    suffix = Path(uploaded.name).suffix.lower()
    try:
        if suffix in {".sqlite3", ".sqlite", ".db"}:
            import_sqlite_file(uploaded)
            messages.success(request, "بازیابی فایل sqlite با موفقیت انجام شد.")
        elif suffix == ".sql":
            import_sql_dump(uploaded)
            messages.success(request, "بازیابی فایل sql با موفقیت انجام شد.")
        else:
            messages.error(request, "فقط فایل‌های sql یا sqlite پشتیبانی می‌شوند.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("entries:features")


@login_required
def project_import(request, pk: int):
    project = get_project_for_user(request.user, pk)
    if request.method != "POST":
        raise Http404
    form = ImportFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "فایل ورودی معتبر نیست.")
        return redirect("entries:project_detail", pk=project.pk)
    try:
        phrases = read_phrases_from_upload(form.cleaned_data["file"])
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("entries:project_detail", pk=project.pk)
    if not phrases:
        messages.warning(request, "هیچ عبارتی برای درون ریزی پیدا نشد.")
        return redirect("entries:project_detail", pk=project.pk)
    start = next_row_number(project.entries)
    entries = [build_project_entry(project, request.user, phrase, row_number=start + index) for index, phrase in enumerate(phrases)]
    ProjectEntry.objects.bulk_create(entries)
    messages.success(request, f"{len(entries)} رکورد از فایل به جدول افزوده شد.")
    return redirect("entries:project_detail", pk=project.pk)


@login_required
def project_export(request, pk: int, file_format: str):
    project = get_project_for_user(request.user, pk)
    entries, _, _, _ = get_table_queryset(request, project.entries.all())
    safe_name = project.name.replace(" ", "_")
    if file_format == "csv":
        content = build_csv_content(entries)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.csv"'
        return response
    if file_format == "xlsm":
        workbook = build_excel_workbook(entries, project.name)
        buffer = BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.ms-excel.sheet.macroEnabled.12",
        )
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.xlsm"'
        return response
    raise Http404


@login_required
def project_entry_edit(request, pk: int):
    entry = get_object_or_404(ProjectEntry.objects.select_related("project"), pk=pk)
    if not entry.project.user_can_access(request.user):
        raise Http404
    if not request.user.is_staff and entry.project.owner != request.user:
        raise Http404
    if request.method == "POST":
        before = serialize_project_entry_snapshot(entry)
        form = ProjectEntryEditForm(request.POST, instance=entry)
        if not request.user.is_staff:
            form.fields.pop("review_status")
            form.fields.pop("review_note")
        if form.is_valid():
            updated = form.save(commit=False)
            result = calculate_phrase(form.cleaned_data["phrase"])
            for field, value in result.as_model_data().items():
                setattr(updated, field, value)
            if request.user.is_staff:
                updated.reviewed_by = request.user
            updated.save()
            record_change(
                request.user,
                ChangeLog.Action.UPDATE,
                ChangeLog.TargetModel.PROJECT_ENTRY,
                updated.phrase,
                before=before,
                after=serialize_project_entry_snapshot(updated),
                target_pk=updated.pk,
            )
            messages.success(request, "رکورد با موفقیت ویرایش شد.")
            return redirect("entries:project_detail", pk=entry.project_id)
    else:
        form = ProjectEntryEditForm(instance=entry)
        if not request.user.is_staff:
            form.fields.pop("review_status")
            form.fields.pop("review_note")
    return render(request, "entries/entry_form.html", {"form": form, "title": "ویرایش رکورد", "back_url": entry.project.get_absolute_url() if hasattr(entry.project, "get_absolute_url") else ""})


@login_required
def project_entry_inline_update(request, pk: int):
    if request.method != "POST":
        raise Http404
    entry = get_object_or_404(ProjectEntry.objects.select_related("project"), pk=pk)
    if not entry.project.user_can_access(request.user):
        raise Http404
    field_name = request.POST.get("field", "").strip()
    raw_value = request.POST.get("value", "")
    if field_name not in INLINE_EDITABLE_FIELDS:
        return JsonResponse({"ok": False, "error": "این ستون قابل ویرایش سریع نیست."}, status=400)
    try:
        with transaction.atomic():
            before = serialize_project_entry_snapshot(entry)
            if field_name == "phrase":
                invalid_chars = find_invalid_phrase_chars(raw_value)
                if invalid_chars:
                    return JsonResponse(
                        {"ok": False, "error": f"کاراکترهای نامعتبر: {' '.join(invalid_chars)}"},
                        status=400,
                    )
                result = calculate_phrase(raw_value)
                for key, value in result.as_model_data().items():
                    setattr(entry, key, value)
                entry.phrase = result.phrase
            else:
                setattr(entry, field_name, cast_inline_value(ProjectEntry, field_name, raw_value))
            entry.save()
            sync_main_entry_from_project_entry(entry)
            entry.has_mismatch, entry.mismatch_fields = detect_entry_mismatch(entry)
            record_change(
                request.user,
                ChangeLog.Action.UPDATE,
                ChangeLog.TargetModel.PROJECT_ENTRY,
                entry.phrase,
                before=before,
                after=serialize_project_entry_snapshot(entry),
                target_pk=entry.pk,
            )
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "مقدار وارد شده معتبر نیست."}, status=400)
    except Exception:
        return JsonResponse({"ok": False, "error": "ذخیره این مقدار ممکن نشد."}, status=400)
    return JsonResponse({"ok": True, "row": serialize_project_entry(entry)})


@staff_required
def project_entry_approve(request, pk: int):
    entry = get_object_or_404(ProjectEntry.objects.select_related("project"), pk=pk)
    if hasattr(entry, "main_entry"):
        messages.info(request, "این رکورد قبلا به جدول اصلی منتقل شده است.")
        return redirect("entries:review_queue")
    with transaction.atomic():
        main_entry = build_main_entry(
            request.user,
            entry.phrase,
            row_number=next_row_number(MainEntry.objects),
            source_project=entry.project,
            source_entry=entry,
        )
        main_entry.save()
        entry.approve(request.user, main_entry)
    messages.success(request, "رکورد با موفقیت به جدول اصلی منتقل شد.")
    return redirect("entries:review_queue")


@staff_required
def project_entry_reject(request, pk: int):
    entry = get_object_or_404(ProjectEntry, pk=pk)
    entry.review_status = ProjectEntry.ReviewStatus.REJECTED
    entry.reviewed_by = request.user
    entry.reviewed_at = timezone.now()
    entry.review_note = request.POST.get("review_note", "").strip()
    entry.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "review_note"])
    messages.warning(request, "رکورد رد شد.")
    return redirect("entries:review_queue")


@login_required
def main_table(request):
    if not user_can_access_main_table(request.user):
        raise Http404("شما به جدول اصلی دسترسی ندارید.")
    entries, q, sort, direction = get_table_queryset(request, MainEntry.objects.select_related("source_project", "published_by"))
    page_obj = paginate_queryset(request, entries)
    annotate_entry_mismatches(page_obj.object_list)
    return render(
        request,
        "entries/main_table.html",
        {
            "page_obj": page_obj,
            "q": q,
            "sort": sort,
            "direction": direction,
            "headers": EXPORT_HEADERS,
            "import_form": ImportFileForm(),
            "filter_rows": get_filter_rows(request),
            "filter_fields": FILTER_FIELD_DEFINITIONS,
            "filter_operators": FILTER_OPERATORS,
        },
    )


@staff_required
def main_bulk_action(request):
    if request.method != "POST":
        raise Http404
    action = request.POST.get("bulk_action", "").strip()
    entries = get_bulk_entries(request, MainEntry.objects.order_by("row_number", "pk"))
    if not entries:
        messages.warning(request, "هیچ عبارتی انتخاب نشده است.")
        return redirect("entries:main_table")
    selected_ids = [entry.pk for entry in entries]
    if action == "delete":
        snapshots = [serialize_main_entry_snapshot(entry) for entry in entries]
        deleted_count, _ = MainEntry.objects.filter(pk__in=selected_ids).delete()
        for snapshot in snapshots:
            record_change(
                request.user,
                ChangeLog.Action.DELETE,
                ChangeLog.TargetModel.MAIN_ENTRY,
                snapshot["phrase"],
                before=snapshot,
                target_pk=snapshot["pk"],
            )
        resequence_main_entries()
        messages.success(request, f"{deleted_count} رکورد از جدول اصلی حذف شد.")
        return redirect("entries:main_table")
    messages.warning(request, "عملیات گروهی انتخاب نشده است.")
    return redirect("entries:main_table")


@staff_required
def main_import(request):
    if request.method != "POST":
        raise Http404
    form = ImportFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "فایل ورودی معتبر نیست.")
        return redirect("entries:main_table")
    try:
        phrases = read_phrases_from_upload(form.cleaned_data["file"])
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("entries:main_table")
    start = next_row_number(MainEntry.objects)
    entries = [build_main_entry(request.user, phrase, row_number=start + index) for index, phrase in enumerate(phrases)]
    MainEntry.objects.bulk_create(entries)
    messages.success(request, f"{len(entries)} رکورد به جدول اصلی افزوده شد.")
    return redirect("entries:main_table")


@login_required
def main_export(request, file_format: str):
    if not user_can_access_main_table(request.user):
        raise Http404("شما به جدول اصلی دسترسی ندارید.")
    entries, _, _, _ = get_table_queryset(request, MainEntry.objects.all())
    if file_format == "csv":
        content = build_csv_content(entries)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="main-table.csv"'
        return response
    if file_format == "xlsm":
        workbook = build_excel_workbook(entries, "Main Table")
        buffer = BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.ms-excel.sheet.macroEnabled.12",
        )
        response["Content-Disposition"] = 'attachment; filename="main-table.xlsm"'
        return response
    raise Http404


@staff_required
def main_entry_edit(request, pk: int):
    entry = get_object_or_404(MainEntry, pk=pk)
    if request.method == "POST":
        before = serialize_main_entry_snapshot(entry)
        form = MainEntryEditForm(request.POST, instance=entry)
        if form.is_valid():
            updated = form.save(commit=False)
            result = calculate_phrase(form.cleaned_data["phrase"])
            for field, value in result.as_model_data().items():
                setattr(updated, field, value)
            updated.save()
            record_change(
                request.user,
                ChangeLog.Action.UPDATE,
                ChangeLog.TargetModel.MAIN_ENTRY,
                updated.phrase,
                before=before,
                after=serialize_main_entry_snapshot(updated),
                target_pk=updated.pk,
            )
            messages.success(request, "رکورد جدول اصلی ویرایش شد.")
            return redirect("entries:main_table")
    else:
        form = MainEntryEditForm(instance=entry)
    return render(request, "entries/entry_form.html", {"form": form, "title": "ویرایش رکورد جدول اصلی"})


@staff_required
def main_entry_inline_update(request, pk: int):
    if request.method != "POST":
        raise Http404
    entry = get_object_or_404(MainEntry, pk=pk)
    field_name = request.POST.get("field", "").strip()
    raw_value = request.POST.get("value", "")
    if field_name not in INLINE_EDITABLE_FIELDS:
        return JsonResponse({"ok": False, "error": "این ستون قابل ویرایش سریع نیست."}, status=400)
    try:
        before = serialize_main_entry_snapshot(entry)
        if field_name == "phrase":
            invalid_chars = find_invalid_phrase_chars(raw_value)
            if invalid_chars:
                return JsonResponse(
                    {"ok": False, "error": f"کاراکترهای نامعتبر: {' '.join(invalid_chars)}"},
                    status=400,
                )
            result = calculate_phrase(raw_value)
            for key, value in result.as_model_data().items():
                setattr(entry, key, value)
            entry.phrase = result.phrase
        else:
            setattr(entry, field_name, cast_inline_value(MainEntry, field_name, raw_value))
        entry.save()
        entry.has_mismatch, entry.mismatch_fields = detect_entry_mismatch(entry)
        record_change(
            request.user,
            ChangeLog.Action.UPDATE,
            ChangeLog.TargetModel.MAIN_ENTRY,
            entry.phrase,
            before=before,
            after=serialize_main_entry_snapshot(entry),
            target_pk=entry.pk,
        )
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "مقدار وارد شده معتبر نیست."}, status=400)
    except Exception:
        return JsonResponse({"ok": False, "error": "ذخیره این مقدار ممکن نشد."}, status=400)
    return JsonResponse({"ok": True, "row": serialize_main_entry(entry)})


@staff_required
def user_management(request):
    users = User.objects.order_by("username").annotate(project_total=Count("owned_projects"))
    return render(request, "entries/user_management.html", {"users": users})


@staff_required
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "کاربر جدید با موفقیت ساخته شد.")
            return redirect("entries:user_management")
    else:
        form = UserCreateForm()
    return render(request, "entries/entry_form.html", {"form": form, "title": "ایجاد کاربر"})


@staff_required
def user_update(request, pk: int):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        before = serialize_user_snapshot(user)
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            record_change(
                request.user,
                ChangeLog.Action.UPDATE,
                ChangeLog.TargetModel.USER,
                user.username,
                before=before,
                after=serialize_user_snapshot(user),
                target_pk=user.pk,
            )
            messages.success(request, "اطلاعات کاربر به روز شد.")
            return redirect("entries:user_management")
    else:
        form = UserUpdateForm(instance=user)
    return render(request, "entries/entry_form.html", {"form": form, "title": f"ویرایش {user.username}"})


@staff_required
def user_delete(request, pk: int):
    if request.method != "POST":
        raise Http404
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "امکان حذف حساب کاربری فعلی شما وجود ندارد.")
        return redirect("entries:user_management")
    if user.owned_projects.exists():
        messages.error(request, "این کاربر هنوز مالک جدول است. ابتدا جدول‌ها را حذف یا منتقل کنید.")
        return redirect("entries:user_management")
    snapshot = serialize_user_snapshot(user)
    username = user.username
    user.delete()
    record_change(
        request.user,
        ChangeLog.Action.DELETE,
        ChangeLog.TargetModel.USER,
        username,
        before=snapshot,
        target_pk=snapshot["pk"],
    )
    messages.success(request, f"کاربر «{username}» حذف شد.")
    return redirect("entries:user_management")


@login_required
def change_log_undo(request, pk: int):
    if request.method != "POST":
        raise Http404
    log = get_object_or_404(get_recent_change_logs(request.user), pk=pk)
    if log.undone_at:
        messages.info(request, "این تغییر قبلا بازگردانده شده است.")
        return redirect("entries:features")
    try:
        with transaction.atomic():
            if log.target_model == ChangeLog.TargetModel.PROJECT_ENTRY:
                restore_project_entry_snapshot(log.snapshot_before)
            elif log.target_model == ChangeLog.TargetModel.MAIN_ENTRY:
                restore_main_entry_snapshot(log.snapshot_before)
            elif log.target_model == ChangeLog.TargetModel.TABLE_PROJECT:
                restore_project_snapshot(log.snapshot_before)
            elif log.target_model == ChangeLog.TargetModel.USER:
                restore_user_snapshot(log.snapshot_before)
            else:
                raise ValueError("مدل پشتیبانی نمی‌شود.")
            log.undone_at = timezone.now()
            log.undone_by = request.user
            log.save(update_fields=["undone_at", "undone_by"])
    except Exception:
        messages.error(request, "بازگردانی این تغییر ممکن نشد.")
        return redirect("entries:features")
    messages.success(request, "تغییر انتخاب‌شده با موفقیت بازگردانی شد.")
    return redirect("entries:features")


@staff_required
def features_full_backup_export(request):
    payload = build_full_backup_payload()
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = 'attachment; filename="abjad-full-backup.json"'
    return response


@staff_required
def review_queue(request):
    entries = ProjectEntry.objects.select_related("project", "created_by").exclude(review_status=ProjectEntry.ReviewStatus.APPROVED)
    q = request.GET.get("q", "").strip()
    if q:
        entries = entries.filter(Q(phrase__icontains=q) | Q(project__name__icontains=q))
    page_obj = paginate_queryset(request, entries.order_by("project__name", "row_number"), per_page=50)
    return render(request, "entries/review_queue.html", {"page_obj": page_obj, "q": q})

# Create your views here.
