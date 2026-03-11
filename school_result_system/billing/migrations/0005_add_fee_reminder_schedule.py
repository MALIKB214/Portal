from django.db import migrations


def create_fee_reminder_schedule(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=1,
        period="days",
    )

    PeriodicTask.objects.get_or_create(
        name="send-fee-reminders-daily",
        defaults={
            "task": "billing.tasks.send_fee_reminders_task",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_fee_reminder_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="send-fee-reminders-daily").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_financeevent_billing_fin_event_t_07b68b_idx_and_more"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_fee_reminder_schedule, remove_fee_reminder_schedule),
    ]
