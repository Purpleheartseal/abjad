from django.urls import path

from . import views

app_name = "entries"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("پروژه‌ها/", views.project_list, name="project_list"),
    path("پروژه‌ها/جدید/", views.project_create, name="project_create"),
    path("پروژه‌ها/<int:pk>/", views.project_detail, name="project_detail"),
    path("پروژه‌ها/<int:pk>/ویرایش/", views.project_update, name="project_update"),
    path("پروژه‌ها/<int:pk>/حذف/", views.project_delete, name="project_delete"),
    path("پروژه‌ها/<int:pk>/محاسبه/", views.project_calculate, name="project_calculate"),
    path("پروژه‌ها/<int:pk>/افزودن/", views.project_add_entry, name="project_add_entry"),
    path("پروژه‌ها/<int:pk>/عملیات-گروهی/", views.project_bulk_action, name="project_bulk_action"),
    path("پروژه‌ها/<int:pk>/درون‌ریزی/", views.project_import, name="project_import"),
    path("پروژه‌ها/<int:pk>/برون‌ریزی/<str:file_format>/", views.project_export, name="project_export"),
    path("رکورد/<int:pk>/ویرایش/", views.project_entry_edit, name="project_entry_edit"),
    path("رکورد/<int:pk>/ویرایش-سریع/", views.project_entry_inline_update, name="project_entry_inline_update"),
    path("رکورد/<int:pk>/تایید/", views.project_entry_approve, name="project_entry_approve"),
    path("رکورد/<int:pk>/رد/", views.project_entry_reject, name="project_entry_reject"),
    path("جدول-اصلی/", views.main_table, name="main_table"),
    path("جدول-اصلی/عملیات-گروهی/", views.main_bulk_action, name="main_bulk_action"),
    path("جدول-اصلی/درون‌ریزی/", views.main_import, name="main_import"),
    path("جدول-اصلی/برون‌ریزی/<str:file_format>/", views.main_export, name="main_export"),
    path("جدول-اصلی/<int:pk>/ویرایش/", views.main_entry_edit, name="main_entry_edit"),
    path("جدول-اصلی/<int:pk>/ویرایش-سریع/", views.main_entry_inline_update, name="main_entry_inline_update"),
    path("امکانات/", views.features, name="features"),
    path("امکانات/حذف-تکراری/", views.features_duplicates_delete, name="features_duplicates_delete"),
    path("امکانات/دیتابیس/ورود/", views.features_database_import, name="features_database_import"),
    path("امکانات/دیتابیس/خروجی/<str:file_format>/", views.features_database_export, name="features_database_export"),
    path("امکانات/بکاپ-کامل/", views.features_full_backup_export, name="features_full_backup_export"),
    path("امکانات/تغییرات/<int:pk>/بازگردانی/", views.change_log_undo, name="change_log_undo"),
    path("مدیریت/کاربران/", views.user_management, name="user_management"),
    path("مدیریت/کاربران/جدید/", views.user_create, name="user_create"),
    path("مدیریت/کاربران/<int:pk>/ویرایش/", views.user_update, name="user_update"),
    path("مدیریت/کاربران/<int:pk>/حذف/", views.user_delete, name="user_delete"),
    path("مدیریت/بررسی/", views.review_queue, name="review_queue"),
]
