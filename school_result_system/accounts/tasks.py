import io

from celery import shared_task
from django.core.management import call_command


@shared_task
def backup_database_task():
    output = io.StringIO()
    call_command("backup_db", stdout=output)
    return output.getvalue()[:500]

