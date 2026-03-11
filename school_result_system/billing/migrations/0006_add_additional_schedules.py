from django.db import migrations


def create_additional_schedules(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    daily, _ = IntervalSchedule.objects.get_or_create(
        every=1,
        period="days",
    )
    weekly, _ = IntervalSchedule.objects.get_or_create(
        every=7,
        period="days",
    )

    PeriodicTask.objects.get_or_create(
        name="send-release-reminders-daily",
        defaults={
            "task": "results.tasks.send_release_reminders_task",
            "interval": daily,
            "enabled": True,
        },
    )

    PeriodicTask.objects.get_or_create(
        name="send-weekly-finance-summary",
        defaults={
            "task": "billing.tasks.send_weekly_finance_summary_task",
            "interval": weekly,
            "enabled": True,
        },
    )


def remove_additional_schedules(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        name__in=["send-release-reminders-daily", "send-weekly-finance-summary"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_add_fee_reminder_schedule"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_additional_schedules, remove_additional_schedules),
    ]
