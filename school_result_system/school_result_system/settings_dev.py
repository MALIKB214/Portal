from .settings import *  # noqa

DEBUG = True
CANONICAL_HOST = ""
CANONICAL_SCHEME = "http"
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# In dev, force SMTP so notification flow matches production behavior.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("DJANGO_EMAIL_USE_SSL", "0") == "1"
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "adebayomalik214@gmail.com")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "dejm isfy upvj zmds")
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
EMAIL_NOTIFICATIONS_ENABLED = os.getenv("DJANGO_EMAIL_NOTIFICATIONS_ENABLED", "1") == "1"

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError("Set only one of DJANGO_EMAIL_USE_TLS=1 or DJANGO_EMAIL_USE_SSL=1.")

# Celery local dev (no Redis): filesystem broker
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "filesystem://")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "data_folder_in": str(BASE_DIR / "celerybroker" / "in"),
    "data_folder_out": str(BASE_DIR / "celerybroker" / "out"),
    "data_folder_processed": str(BASE_DIR / "celerybroker" / "processed"),
}
