from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0009_notification_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentdomainassessment",
            name="next_term_begins",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="studentdomainassessment",
            name="principal_remark",
            field=models.CharField(blank=True, max_length=220),
        ),
        migrations.AddField(
            model_name="studentdomainassessment",
            name="times_absent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="studentdomainassessment",
            name="times_present",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="studentdomainassessment",
            name="times_school_opened",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
