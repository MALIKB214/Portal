from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_systemeventlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="role",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="intended_class",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reason",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="preferred_contact",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
