from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0002_term"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="short_name",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]

