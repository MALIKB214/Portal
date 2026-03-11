from django.db import migrations


def sync_flags_from_groups(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Group = apps.get_model("auth", "Group")

    bursar_group = Group.objects.filter(name="Bursar").first()
    principal_group = Group.objects.filter(name="Principal").first()

    if bursar_group:
        User.objects.filter(groups=bursar_group).update(is_bursar=True)
    if principal_group:
        User.objects.filter(groups=principal_group).update(is_principal=True)


def reverse_sync_flags(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.update(is_bursar=False, is_principal=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_user_bursar_principal_flags"),
    ]

    operations = [
        migrations.RunPython(sync_flags_from_groups, reverse_sync_flags),
    ]

