try:
    from .celery import app as celery_app  # type: ignore
    __all__ = ("celery_app",)
except Exception:
    celery_app = None
    __all__ = ()
