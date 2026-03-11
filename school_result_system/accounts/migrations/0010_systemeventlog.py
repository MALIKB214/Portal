from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_rename_accounts_st_user_id_3dcd8a_idx_accounts_st_user_id_758b1f_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemEventLog",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=80)),
                ("detail", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="systemeventlog",
            index=models.Index(fields=("action", "-created_at"), name="accounts_sy_action_6b9ee0_idx"),
        ),
    ]
