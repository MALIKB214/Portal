from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_schoolbranding_report_designer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolbranding",
            name="report_print_density",
            field=models.CharField(
                choices=[("standard", "Standard"), ("dense", "High Density")],
                default="standard",
                max_length=16,
            ),
        ),
    ]

