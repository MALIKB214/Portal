from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_alter_contactmessage_id_alter_schoolbranding_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffNotification",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("results", "Results"),
                            ("finance", "Finance"),
                            ("account", "Account"),
                            ("system", "System"),
                        ],
                        default="system",
                        max_length=20,
                    ),
                ),
                ("message", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_read", models.BooleanField(default=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="staffnotification",
            index=models.Index(fields=["user", "is_read"], name="accounts_st_user_id_3dcd8a_idx"),
        ),
        migrations.AddIndex(
            model_name="staffnotification",
            index=models.Index(fields=["category", "-created_at"], name="accounts_st_category_4e8c73_idx"),
        ),
    ]
