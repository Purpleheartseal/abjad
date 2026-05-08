from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class PersianAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="نام کاربری")
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = [
            "username",
            "display_name",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "can_access_main_table",
            "is_active",
        ]
        labels = {
            "username": "نام کاربری",
            "display_name": "نام نمایشی",
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "email": "ایمیل",
            "is_staff": "مدیر باشد",
            "can_access_main_table": "دسترسی به جدول اصلی داشته باشد",
            "is_active": "فعال باشد",
        }


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name", "first_name", "last_name", "email", "is_staff", "can_access_main_table", "is_active"]
        labels = {
            "display_name": "نام نمایشی",
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "email": "ایمیل",
            "is_staff": "مدیر باشد",
            "can_access_main_table": "دسترسی به جدول اصلی داشته باشد",
            "is_active": "فعال باشد",
        }
