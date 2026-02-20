from django.contrib import admin
from django.core.exceptions import PermissionDenied
from .models import Result, ResultAudit, ResultRelease, Notification


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "subject",
        "session",
        "term",
        "status",
        "ca1",
        "ca2",
        "ca3",
        "project",
        "exam",
        "total_score",
        "grade",
    )
    list_filter = ("session", "term", "subject", "status")
    search_fields = ("student__first_name", "student__last_name", "student__admission_number")

    def save_model(self, request, obj, form, change):
        if change:
            previous = Result.objects.filter(pk=obj.pk).first()
            old_status = previous.status if previous else None
            is_approving = old_status != Result.STATUS_APPROVED and obj.status == Result.STATUS_APPROVED
            if is_approving:
                can_approve = (
                    getattr(request.user, "is_proprietor", False)
                    or getattr(request.user, "is_admin", False)
                    or getattr(request.user, "is_superuser", False)
                )
                if not can_approve:
                    raise PermissionDenied("Only proprietor/admin can approve results.")
                obj.approved_by = request.user
                if not obj.approved_at:
                    from django.utils import timezone
                    obj.approved_at = timezone.now()

        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ResultAudit)
class ResultAuditAdmin(admin.ModelAdmin):
    list_display = ("result", "changed_by", "changed_at")
    list_filter = ("changed_at",)


@admin.register(ResultRelease)
class ResultReleaseAdmin(admin.ModelAdmin):
    list_display = ("session", "term", "class_name", "released_by", "released_at")
    list_filter = ("session", "term")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "term", "message", "created_at", "is_read")
    list_filter = ("session", "term", "is_read")
