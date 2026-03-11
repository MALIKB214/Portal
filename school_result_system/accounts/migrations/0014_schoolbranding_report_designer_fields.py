from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_schoolbranding_promotion_policy_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolbranding",
            name="principal_signature_file",
            field=models.FileField(blank=True, null=True, upload_to="branding/signatures/"),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="class_teacher_signature_file",
            field=models.FileField(blank=True, null=True, upload_to="branding/signatures/"),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="grading_template",
            field=models.CharField(
                choices=[("custom", "Custom"), ("waec", "WAEC Standard"), ("strict", "Strict Senior")],
                default="custom",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="report_template_style",
            field=models.CharField(
                choices=[("classic", "Classic"), ("compact", "Compact")],
                default="classic",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="result_footer_note",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
