from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    display_name = models.CharField("نام نمایشی", max_length=150, blank=True)
    can_access_main_table = models.BooleanField("دسترسی به جدول اصلی", default=False)

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self) -> str:
        return self.display_name or self.get_full_name() or self.username

    @property
    def can_view_main_table(self) -> bool:
        return self.is_staff or self.can_access_main_table

# Create your models here.
