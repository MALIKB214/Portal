from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_rolecapabilitypolicy"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_bursar",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="is_principal",
            field=models.BooleanField(default=False),
        ),
    ]

