from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0010_studentdomainassessment_attendance_and_remarks"),
        ("academics", "0003_subject_short_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResultSnapshot",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("content_hash", models.CharField(max_length=64)),
                ("signature", models.CharField(max_length=64)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("invalidation_reason", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="result_snapshots_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invalidated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="result_snapshots_invalidated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school_class",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.schoolclass",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.academicsession",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.term",
                    ),
                ),
                (
                    "workflow",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="snapshots",
                        to="results.resultworkflow",
                    ),
                ),
            ],
            options={
                "ordering": ("school_class__name",),
                "indexes": [
                    models.Index(fields=["session", "term", "school_class"], name="results_res_session_53a8d4_idx"),
                    models.Index(fields=["invalidated_at"], name="results_res_invalid_9d12a4_idx"),
                ],
                "unique_together": {("session", "term", "school_class")},
            },
        ),
        migrations.CreateModel(
            name="ResultReopenLog",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("reason", models.CharField(blank=True, max_length=240)),
                ("previous_hash", models.CharField(blank=True, max_length=64)),
                ("reopened_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reopened_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school_class",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.schoolclass",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.academicsession",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.term",
                    ),
                ),
            ],
            options={
                "ordering": ("-reopened_at",),
                "indexes": [
                    models.Index(fields=["session", "term", "school_class"], name="results_res_session_664dd8_idx"),
                ],
            },
        ),
    ]

