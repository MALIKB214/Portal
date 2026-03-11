from django.conf import settings
from django.core.checks import run_checks
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Runs a lightweight production readiness baseline check."

    def handle(self, *args, **options):
        errors = []

        self.stdout.write(self.style.NOTICE("Running Django system checks..."))
        check_messages = run_checks()
        for msg in check_messages:
            if msg.level >= 30:
                errors.append(f"System check: {msg.msg}")

        self.stdout.write(self.style.NOTICE("Checking database connectivity..."))
        connection = connections["default"]
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            errors.append(f"Database check failed: {exc}")

        self.stdout.write(self.style.NOTICE("Checking pending migrations..."))
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            errors.append("Pending migrations detected. Run `python manage.py migrate`.")

        self.stdout.write(self.style.NOTICE("Checking core production settings..."))
        if settings.DEBUG:
            errors.append("DEBUG is enabled.")
        if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ["*"]:
            errors.append("ALLOWED_HOSTS is too permissive.")

        if errors:
            for err in errors:
                self.stderr.write(self.style.ERROR(f"- {err}"))
            raise CommandError("Readiness check failed.")

        self.stdout.write(self.style.SUCCESS("Readiness check passed."))
