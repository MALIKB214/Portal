from django.db import migrations


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    bursar_group, _ = Group.objects.get_or_create(name="Bursar")
    principal_group, _ = Group.objects.get_or_create(name="Principal")
    teacher_group, _ = Group.objects.get_or_create(name="Teacher")
    student_group, _ = Group.objects.get_or_create(name="Student/Parent")

    perms = Permission.objects.filter(
        content_type__app_label="billing",
        codename__in=[
            "view_invoice",
            "add_invoice",
            "change_invoice",
            "view_invoiceitem",
            "add_invoiceitem",
            "change_invoiceitem",
            "view_payment",
            "add_payment",
            "change_payment",
        ],
    )
    bursar_group.permissions.add(*perms)

    monitor_perms = Permission.objects.filter(
        content_type__app_label="billing",
        codename__in=["view_invoice", "view_invoiceitem", "view_payment"],
    )
    principal_group.permissions.add(*monitor_perms)


def reverse_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["Bursar", "Principal", "Teacher", "Student/Parent"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_contactmessage_schoolbranding_alter_user_id"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, reverse_role_groups),
    ]
