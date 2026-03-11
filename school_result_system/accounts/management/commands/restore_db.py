import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Restore sqlite database from a backup file."

    def add_arguments(self, parser):
        parser.add_argument("backup_path", type=str)
        parser.add_argument("--yes", action="store_true", help="Confirm restore (destructive).")

    def handle(self, *args, **options):
        if not options["yes"]:
            self.stderr.write(self.style.ERROR("Add --yes to confirm restore operation."))
            return

        backup_path = Path(options["backup_path"])
        db_path = Path(settings.DATABASES["default"]["NAME"])

        if not backup_path.exists():
            self.stderr.write(self.style.ERROR(f"Backup file not found: {backup_path}"))
            return

        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, db_path)
        self.stdout.write(self.style.SUCCESS(f"Database restored from {backup_path}"))
