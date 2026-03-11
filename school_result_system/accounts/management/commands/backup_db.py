import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backup sqlite database file into backups/ folder."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", type=str, default="backups")
        parser.add_argument("--filename", type=str, default="")

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f"Database file not found: {db_path}"))
            return

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = options["filename"] or f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
        target_path = output_dir / filename
        shutil.copy2(db_path, target_path)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {target_path}"))
