from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from results.models import ParentPortalAccount
from students.models import Student


class Command(BaseCommand):
    help = "Provision parent portal username/password accounts for students with parent_email."

    def add_arguments(self, parser):
        parser.add_argument("--default-password", type=str, default="Parent@123")
        parser.add_argument("--only-missing", action="store_true")

    def handle(self, *args, **options):
        User = get_user_model()
        qs = Student.objects.exclude(parent_email="").order_by("id")
        if options["only_missing"]:
            qs = qs.filter(parent_portal_account__isnull=True)

        created = 0
        linked = 0
        for student in qs:
            username = f"parent_{student.admission_number.replace('/', '').lower()}"
            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": student.parent_email,
                    "first_name": "Parent",
                    "last_name": student.last_name or student.first_name,
                },
            )
            if user_created:
                user.set_password(options["default_password"])
                user.save(update_fields=["password"])
                created += 1
            ParentPortalAccount.objects.get_or_create(
                user=user,
                student=student,
                defaults={"is_active": True},
            )
            linked += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Provisioned parent accounts. Users created: {created}, students linked: {linked}."
            )
        )
