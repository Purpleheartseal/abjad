from django.conf import settings
from django.db import models
from django.utils import timezone
from django.urls import reverse


class TableProject(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        ARCHIVED = "archived", "بایگانی"

    name = models.CharField("نام جدول", max_length=200)
    description = models.TextField("توضیحات", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="مالک",
        on_delete=models.CASCADE,
        related_name="owned_projects",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربران مجاز",
        related_name="assigned_projects",
        blank=True,
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField("ایجاد شده در", auto_now_add=True)
    updated_at = models.DateTimeField("به روز شده در", auto_now=True)

    class Meta:
        verbose_name = "جدول پروژه"
        verbose_name_plural = "جدول های پروژه"
        ordering = ["-updated_at", "name"]

    def __str__(self) -> str:
        return self.name

    def user_can_access(self, user) -> bool:
        if not user.is_authenticated:
            return False
        return user.is_staff or user == self.owner or self.members.filter(pk=user.pk).exists()

    def get_absolute_url(self):
        return reverse("entries:project_detail", kwargs={"pk": self.pk})


class CalculatedFieldsMixin(models.Model):
    phrase = models.CharField("عبارت", max_length=500)
    normalized_phrase = models.CharField("عبارت نرمال شده", max_length=500, editable=False)
    abjad_value = models.PositiveIntegerField("عدد ابجد", default=0)
    prime_index = models.PositiveIntegerField("چندمین عدد اول", default=0)
    digit_root = models.PositiveSmallIntegerField("ریشه عدد", default=0)
    abjad_sum = models.PositiveBigIntegerField("مجموع عدد ابجد", default=0)
    parity_label = models.CharField("زوج یا فرد", max_length=10, blank=True)
    parity_order = models.PositiveIntegerField("چندمین زوج فرد", default=0)
    letter_count = models.PositiveIntegerField("تعداد حروف", default=0)
    dot_count = models.PositiveIntegerField("تعداد نقطه", default=0)
    unique_letter_count = models.PositiveIntegerField("تعداد حروف یکتا", default=0)
    used_letters = models.CharField("حروف استفاده شده", max_length=500, blank=True)
    pronounced_value = models.PositiveIntegerField("عدد ملفوظی", default=0)
    alif_count = models.PositiveIntegerField("تعداد الف", default=0)
    abjad_saghir = models.PositiveIntegerField("ابجد صغیر", default=0)
    breakdown = models.TextField("تبدیل حرف به عدد", blank=True)
    created_at = models.DateTimeField("ایجاد شده در", auto_now_add=True)
    updated_at = models.DateTimeField("به روز شده در", auto_now=True)

    class Meta:
        abstract = True


class ProjectEntry(CalculatedFieldsMixin):
    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "پیش نویس"
        APPROVED = "approved", "تایید شده"
        REJECTED = "rejected", "رد شده"

    project = models.ForeignKey(
        TableProject,
        verbose_name="جدول پروژه",
        on_delete=models.CASCADE,
        related_name="entries",
    )
    row_number = models.PositiveIntegerField("ردیف", default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ثبت کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_entries",
    )
    review_status = models.CharField(
        "وضعیت بررسی",
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.DRAFT,
    )
    review_note = models.TextField("یادداشت بررسی", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="بررسی کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_project_entries",
    )
    reviewed_at = models.DateTimeField("زمان بررسی", null=True, blank=True)

    class Meta:
        verbose_name = "رکورد پروژه"
        verbose_name_plural = "رکوردهای پروژه"
        ordering = ["row_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "row_number"],
                name="unique_project_row_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.name} - {self.phrase}"

    def approve(self, reviewer, main_entry):
        self.review_status = self.ReviewStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = ""
        self.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "review_note"])
        main_entry.source_entry = self
        main_entry.save(update_fields=["source_entry"])


class MainEntry(CalculatedFieldsMixin):
    row_number = models.PositiveIntegerField("ردیف", default=0, unique=True)
    source_project = models.ForeignKey(
        TableProject,
        verbose_name="پروژه مبدا",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_entries",
    )
    source_entry = models.OneToOneField(
        ProjectEntry,
        verbose_name="رکورد مبدا",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="main_entry",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="منتشر کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_main_entries",
    )

    class Meta:
        verbose_name = "رکورد جدول اصلی"
        verbose_name_plural = "رکوردهای جدول اصلی"
        ordering = ["row_number", "id"]

    def __str__(self) -> str:
        return self.phrase


class ChangeLog(models.Model):
    class Action(models.TextChoices):
        UPDATE = "update", "ویرایش"
        DELETE = "delete", "حذف"

    class TargetModel(models.TextChoices):
        PROJECT_ENTRY = "project_entry", "رکورد پروژه"
        MAIN_ENTRY = "main_entry", "رکورد جدول اصلی"
        TABLE_PROJECT = "table_project", "جدول پروژه"
        USER = "user", "کاربر"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="انجام دهنده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_logs",
    )
    action = models.CharField("نوع تغییر", max_length=20, choices=Action.choices)
    target_model = models.CharField("مدل هدف", max_length=30, choices=TargetModel.choices)
    target_pk = models.PositiveIntegerField("شناسه هدف", null=True, blank=True)
    target_label = models.CharField("عنوان هدف", max_length=255, blank=True)
    snapshot_before = models.JSONField("وضعیت قبل", default=dict, blank=True)
    snapshot_after = models.JSONField("وضعیت بعد", default=dict, blank=True)
    created_at = models.DateTimeField("زمان تغییر", auto_now_add=True)
    undone_at = models.DateTimeField("زمان بازگشت", null=True, blank=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="بازگرداننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="undone_change_logs",
    )

    class Meta:
        verbose_name = "تغییر اخیر"
        verbose_name_plural = "تغییرات اخیر"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.get_target_model_display()} {self.target_label}".strip()

# Create your models here.
