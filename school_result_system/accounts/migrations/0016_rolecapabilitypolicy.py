from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_schoolbranding_report_print_density"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleCapabilityPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("teacher", "Teacher"),
                            ("bursar", "Bursar"),
                            ("principal", "Principal"),
                            ("proprietor", "Proprietor"),
                            ("admin", "Admin"),
                        ],
                        max_length=20,
                    ),
                ),
                ("capability", models.CharField(max_length=80)),
                ("is_allowed", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Role Capability Policy",
                "verbose_name_plural": "Role Capability Policies",
                "ordering": ("role", "capability"),
                "unique_together": {("role", "capability")},
            },
        ),
    ]

