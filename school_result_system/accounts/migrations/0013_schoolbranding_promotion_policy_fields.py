from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_contactmessage_more_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolbranding",
            name="promotion_min_attendance_rate",
            field=models.FloatField(default=75.0),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="promotion_min_behavior_average",
            field=models.FloatField(default=2.5),
        ),
        migrations.AddField(
            model_name="schoolbranding",
            name="promotion_require_non_cognitive",
            field=models.BooleanField(default=True),
        ),
    ]
