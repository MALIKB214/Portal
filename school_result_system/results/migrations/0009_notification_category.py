from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0008_parentportalaccount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="category",
            field=models.CharField(
                choices=[
                    ("results", "Results"),
                    ("finance", "Finance"),
                    ("account", "Account"),
                    ("system", "System"),
                ],
                default="system",
                max_length=20,
            ),
        ),
    ]
