from django import forms

from accounts.forms import UserCreateForm, UserUpdateForm
from accounts.models import User

from .models import MainEntry, ProjectEntry, TableProject
from .services import find_invalid_phrase_chars


def validate_phrase_field(value: str) -> str:
    invalid = find_invalid_phrase_chars(value)
    if invalid:
        raise forms.ValidationError(
            f"فقط حروف استاندارد ابجد مجاز هستند. کاراکترهای نامعتبر: {' '.join(invalid)}"
        )
    return value


class TableProjectForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        label="کاربران مجاز",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = TableProject
        fields = ["name", "description", "owner", "members", "status"]
        labels = {
            "name": "نام جدول",
            "description": "توضیحات",
            "owner": "مالک",
            "status": "وضعیت",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class UserProjectForm(forms.ModelForm):
    class Meta:
        model = TableProject
        fields = ["name", "description"]
        labels = {
            "name": "نام جدول",
            "description": "توضیحات",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class PhraseForm(forms.Form):
    phrase = forms.CharField(label="عبارت", widget=forms.Textarea(attrs={"rows": 3}))

    def clean_phrase(self):
        return validate_phrase_field(self.cleaned_data["phrase"])


class ProjectEntryEditForm(forms.ModelForm):
    class Meta:
        model = ProjectEntry
        fields = ["phrase", "review_status", "review_note"]
        labels = {
            "phrase": "عبارت",
            "review_status": "وضعیت بررسی",
            "review_note": "یادداشت بررسی",
        }
        widgets = {"review_note": forms.Textarea(attrs={"rows": 3})}

    def clean_phrase(self):
        return validate_phrase_field(self.cleaned_data["phrase"])


class MainEntryEditForm(forms.ModelForm):
    class Meta:
        model = MainEntry
        fields = ["phrase"]
        labels = {"phrase": "عبارت"}

    def clean_phrase(self):
        return validate_phrase_field(self.cleaned_data["phrase"])


class ImportFileForm(forms.Form):
    file = forms.FileField(label="فایل")


__all__ = [
    "ImportFileForm",
    "MainEntryEditForm",
    "PhraseForm",
    "ProjectEntryEditForm",
    "TableProjectForm",
    "UserCreateForm",
    "UserProjectForm",
    "UserUpdateForm",
]
