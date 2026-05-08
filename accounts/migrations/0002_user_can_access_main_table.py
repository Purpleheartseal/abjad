from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="can_access_main_table",
            field=models.BooleanField(default=False, verbose_name="دسترسی به جدول اصلی"),
        ),
    ]
