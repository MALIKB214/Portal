import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_result_system.settings")

app = Celery("school_result_system")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
