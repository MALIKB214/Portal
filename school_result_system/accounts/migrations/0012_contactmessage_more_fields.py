from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_contactmessage_extra_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="guardian_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="student_age",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="preferred_visit_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="referral_source",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
