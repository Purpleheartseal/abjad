from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import PhraseForm
from .models import ChangeLog, MainEntry, ProjectEntry, TableProject
from .services import build_duplicate_groups, calculate_phrase, extract_phrases_from_rows
from .views import detect_entry_mismatch


class CalculationServiceTests(TestCase):
    def test_calculate_phrase_matches_known_values(self):
        result = calculate_phrase("سلام").as_model_data()
        self.assertEqual(result["abjad_value"], 131)
        self.assertEqual(result["prime_index"], 32)
        self.assertEqual(result["digit_root"], 5)
        self.assertEqual(result["abjad_sum"], 8646)
        self.assertEqual(result["parity_label"], "فرد")
        self.assertEqual(result["unique_letter_count"], 4)
        self.assertEqual(result["used_letters"], "س - م - ل - ا")
        self.assertEqual(result["pronounced_value"], 392)
        self.assertEqual(result["abjad_saghir"], 11)

    def test_normalizes_arabic_and_persian_keyboards(self):
        arabic = calculate_phrase("علي").as_model_data()
        persian = calculate_phrase("علی").as_model_data()
        self.assertEqual(arabic["abjad_value"], persian["abjad_value"])
        self.assertEqual(arabic["abjad_saghir"], persian["abjad_saghir"])

    def test_extract_phrases_skips_header_noise(self):
        phrases = extract_phrases_from_rows(
            [
                ["رديف", "", "عدد ابجد"],
                [1, "سلام", 131],
                [2, "علي", 110],
            ]
        )
        self.assertEqual(phrases, ["سلام", "علي"])

    def test_duplicate_groups_ignore_spacing_differences(self):
        class Entry:
            def __init__(self, pk, row_number, phrase):
                self.pk = pk
                self.row_number = row_number
                self.phrase = phrase

        groups = build_duplicate_groups(
            [
                Entry(1, 1, "سلام دنیا"),
                Entry(2, 2, "سلام   دنیا"),
                Entry(3, 3, "سلام-دنیا"),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 3)

    def test_phrase_form_rejects_non_standard_letters(self):
        form = PhraseForm(data={"phrase": "گچ"})
        self.assertFalse(form.is_valid())

    def test_phrase_form_allows_special_characters(self):
        form = PhraseForm(data={"phrase": "سلام (علی) - تست..."})
        self.assertTrue(form.is_valid())

    def test_calculation_ignores_special_characters(self):
        plain = calculate_phrase("سلام علی").as_model_data()
        decorated = calculate_phrase("سلام-علی...").as_model_data()
        self.assertEqual(decorated["abjad_value"], plain["abjad_value"])
        self.assertEqual(decorated["letter_count"], plain["letter_count"])
        self.assertEqual(decorated["unique_letter_count"], plain["unique_letter_count"])


class InlineEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="editor", password="secret123")
        self.admin = get_user_model().objects.create_user(
            username="admin",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        self.project = TableProject.objects.create(name="جدول تست", owner=self.user)
        initial = calculate_phrase("سلام").as_model_data()
        self.entry = ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=1,
            **initial,
        )

    def test_project_inline_update_recalculates_phrase(self):
        self.client.login(username="editor", password="secret123")
        response = self.client.post(
            reverse("entries:project_entry_inline_update", args=[self.entry.pk]),
            {"field": "phrase", "value": "علی"},
        )
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.phrase, "علی")
        self.assertEqual(self.entry.abjad_value, 110)
        self.assertEqual(response.json()["row"]["breakdown"], "70+30+10=110")

    def test_main_inline_update_requires_staff(self):
        data = calculate_phrase("سلام").as_model_data()
        main_entry = MainEntry.objects.create(row_number=1, **data)
        self.client.login(username="editor", password="secret123")
        forbidden = self.client.post(
            reverse("entries:main_entry_inline_update", args=[main_entry.pk]),
            {"field": "phrase", "value": "علی"},
        )
        self.assertEqual(forbidden.status_code, 302)
        self.client.login(username="admin", password="secret123")
        allowed = self.client.post(
            reverse("entries:main_entry_inline_update", args=[main_entry.pk]),
            {"field": "phrase", "value": "علی"},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_main_table_requires_explicit_access_for_regular_user(self):
        self.client.login(username="editor", password="secret123")
        response = self.client.get(reverse("entries:main_table"))
        self.assertEqual(response.status_code, 404)

    def test_regular_user_with_main_access_can_view_main_table(self):
        self.user.can_access_main_table = True
        self.user.save(update_fields=["can_access_main_table"])
        MainEntry.objects.create(row_number=1, **calculate_phrase("سلام").as_model_data())
        self.client.login(username="editor", password="secret123")
        response = self.client.get(reverse("entries:main_table"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سلام")

    def test_main_bulk_delete_resequences_row_numbers(self):
        self.client.login(username="admin", password="secret123")
        first = MainEntry.objects.create(row_number=1, **calculate_phrase("سلام").as_model_data())
        second = MainEntry.objects.create(row_number=2, **calculate_phrase("علی").as_model_data())
        third = MainEntry.objects.create(row_number=3, **calculate_phrase("مهدی").as_model_data())
        response = self.client.post(
            reverse("entries:main_bulk_action"),
            {
                "bulk_action": "delete",
                "entry_ids": [second.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(MainEntry.objects.order_by("row_number").values_list("row_number", flat=True)),
            [1, 2],
        )
        self.assertEqual(
            list(MainEntry.objects.order_by("row_number").values_list("phrase", flat=True)),
            [first.phrase, third.phrase],
        )

    def test_main_bulk_delete_can_select_all_filtered_results(self):
        self.client.login(username="admin", password="secret123")
        MainEntry.objects.create(row_number=1, **calculate_phrase("سلام").as_model_data())
        MainEntry.objects.create(row_number=2, **calculate_phrase("سلام دوم").as_model_data())
        MainEntry.objects.create(row_number=3, **calculate_phrase("علی").as_model_data())
        response = self.client.post(
            reverse("entries:main_bulk_action"),
            {
                "bulk_action": "delete",
                "select_all_filtered": "1",
                "q": "سلام",
                "sort": "row_number",
                "direction": "asc",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(MainEntry.objects.values_list("phrase", flat=True)), ["علی"])
        self.assertEqual(list(MainEntry.objects.values_list("row_number", flat=True)), [1])

    def test_features_duplicate_delete_keeps_one_copy(self):
        self.client.login(username="editor", password="secret123")
        duplicate = calculate_phrase("سلام").as_model_data()
        ProjectEntry.objects.create(project=self.project, created_by=self.user, row_number=2, **duplicate)
        ProjectEntry.objects.create(project=self.project, created_by=self.user, row_number=3, **duplicate)
        response = self.client.post(
            reverse("entries:features_duplicates_delete"),
            {
                "source_type": "project",
                "project": self.project.pk,
                "delete_all": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.entries.count(), 1)

    def test_project_delete_removes_table_and_creates_change_log(self):
        self.client.login(username="editor", password="secret123")
        response = self.client.post(reverse("entries:project_delete", args=[self.project.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TableProject.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            ChangeLog.objects.filter(
                action=ChangeLog.Action.DELETE,
                target_model=ChangeLog.TargetModel.TABLE_PROJECT,
                target_pk=self.project.pk,
            ).exists()
        )

    def test_user_delete_requires_no_owned_projects(self):
        self.client.login(username="admin", password="secret123")
        response = self.client.post(reverse("entries:user_delete", args=[self.user.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_staff_can_export_sql_backup(self):
        self.client.login(username="admin", password="secret123")
        response = self.client.get(reverse("entries:features_database_export", args=["sql"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertIn("BEGIN TRANSACTION", response.content.decode("utf-8"))

    def test_staff_can_export_full_backup_json(self):
        self.client.login(username="admin", password="secret123")
        response = self.client.get(reverse("entries:features_full_backup_export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        self.assertIn("users", response.content.decode("utf-8"))

    def test_project_bulk_move_transfers_selected_entries(self):
        self.client.login(username="editor", password="secret123")
        target = TableProject.objects.create(name="جدول مقصد", owner=self.user)
        second = ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=2,
            **calculate_phrase("علی").as_model_data(),
        )
        response = self.client.post(
            reverse("entries:project_bulk_action", args=[self.project.pk]),
            {
                "bulk_action": "move",
                "target_project": target.pk,
                "entry_ids": [self.entry.pk, second.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(target.entries.count(), 2)
        self.assertEqual(self.project.entries.count(), 0)
        self.assertEqual(list(target.entries.order_by("row_number").values_list("row_number", flat=True)), [1, 2])

    def test_project_bulk_delete_resequences_row_numbers(self):
        self.client.login(username="editor", password="secret123")
        second = ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=2,
            **calculate_phrase("علی").as_model_data(),
        )
        third = ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=3,
            **calculate_phrase("مهدی").as_model_data(),
        )
        response = self.client.post(
            reverse("entries:project_bulk_action", args=[self.project.pk]),
            {
                "bulk_action": "delete",
                "entry_ids": [second.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(self.project.entries.order_by("row_number").values_list("row_number", flat=True)),
            [1, 2],
        )
        self.assertEqual(
            list(self.project.entries.order_by("row_number").values_list("phrase", flat=True)),
            ["سلام", "مهدی"],
        )

    def test_project_bulk_delete_can_select_all_filtered_results(self):
        self.client.login(username="editor", password="secret123")
        ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=2,
            **calculate_phrase("سلام دوم").as_model_data(),
        )
        ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=3,
            **calculate_phrase("علی").as_model_data(),
        )
        response = self.client.post(
            reverse("entries:project_bulk_action", args=[self.project.pk]),
            {
                "bulk_action": "delete",
                "select_all_filtered": "1",
                "q": "سلام",
                "sort": "row_number",
                "direction": "asc",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.project.entries.values_list("phrase", flat=True)), ["علی"])
        self.assertEqual(list(self.project.entries.values_list("row_number", flat=True)), [1])

    def test_detect_entry_mismatch_flags_changed_numbers(self):
        self.entry.abjad_value = 999
        has_mismatch, fields = detect_entry_mismatch(self.entry)
        self.assertTrue(has_mismatch)
        self.assertIn("abjad_value", fields)

    def test_detect_entry_mismatch_flags_unique_letter_changes(self):
        self.entry.unique_letter_count = 1
        has_mismatch, fields = detect_entry_mismatch(self.entry)
        self.assertTrue(has_mismatch)
        self.assertIn("unique_letter_count", fields)

    def test_detect_entry_mismatch_flags_invalid_phrase_chars(self):
        self.entry.phrase = "سلامگ"
        has_mismatch, fields = detect_entry_mismatch(self.entry)
        self.assertTrue(has_mismatch)
        self.assertIn("phrase", fields)

    def test_undo_restores_deleted_project_entry(self):
        self.client.login(username="editor", password="secret123")
        delete_response = self.client.post(
            reverse("entries:project_bulk_action", args=[self.project.pk]),
            {
                "bulk_action": "delete",
                "entry_ids": [self.entry.pk],
            },
        )
        self.assertEqual(delete_response.status_code, 302)
        log = ChangeLog.objects.filter(
            action=ChangeLog.Action.DELETE,
            target_model=ChangeLog.TargetModel.PROJECT_ENTRY,
        ).latest("id")
        undo_response = self.client.post(reverse("entries:change_log_undo", args=[log.pk]))
        self.assertEqual(undo_response.status_code, 302)
        self.assertTrue(ProjectEntry.objects.filter(pk=self.entry.pk).exists())

    def test_undo_restores_updated_project_entry_value(self):
        self.client.login(username="editor", password="secret123")
        response = self.client.post(
            reverse("entries:project_entry_inline_update", args=[self.entry.pk]),
            {"field": "phrase", "value": "علی"},
        )
        self.assertEqual(response.status_code, 200)
        log = ChangeLog.objects.filter(
            action=ChangeLog.Action.UPDATE,
            target_model=ChangeLog.TargetModel.PROJECT_ENTRY,
        ).latest("id")
        undo_response = self.client.post(reverse("entries:change_log_undo", args=[log.pk]))
        self.assertEqual(undo_response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.phrase, "سلام")

    def test_project_detail_supports_advanced_filtering(self):
        self.client.login(username="editor", password="secret123")
        ProjectEntry.objects.create(
            project=self.project,
            created_by=self.user,
            row_number=2,
            **calculate_phrase("علی").as_model_data(),
        )
        response = self.client.get(
            reverse("entries:project_detail", args=[self.project.pk]),
            {
                "filter_field_1": "abjad_value",
                "filter_operator_1": "gt",
                "filter_value_1": "120",
                "filter_join_2": "and",
                "filter_field_2": "phrase",
                "filter_operator_2": "contains",
                "filter_value_2": "س",
            },
        )
        self.assertEqual(response.status_code, 200)
        page_entries = list(response.context["page_obj"].object_list)
        self.assertEqual(len(page_entries), 1)
        self.assertEqual(page_entries[0].phrase, "سلام")
