from django.shortcuts import render
from django.db import connections
from django.http import JsonResponse
from django.utils import timezone


def handler403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def handler404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def handler500(request):
    return render(request, "errors/500.html", status=500)


def health_live(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "school_result_system",
            "type": "liveness",
            "timestamp": timezone.now().isoformat(),
        }
    )


def health_ready(request):
    db_ok = True
    db_error = ""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    status_code = 200 if db_ok else 503
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "school_result_system",
            "type": "readiness",
            "database": {"ok": db_ok, "error": db_error},
            "timestamp": timezone.now().isoformat(),
        },
        status=status_code,
    )
