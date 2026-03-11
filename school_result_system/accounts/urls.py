from django.urls import path
from .views import (
    landing_page,
    teacher_login,
    teacher_logout,
    teacher_dashboard,
    proprietor_dashboard,
    setup_wizard,
    analytics_export,
    promotion_analytics_export,
    branding_settings,
    role_permission_matrix,
    staff_notifications,
    staff_mark_notifications_read,
    staff_mark_notification_read,
    parent_email_audit,
    schedule_manager,
    system_health,
)

app_name = "accounts"
urlpatterns = [
    path("", landing_page, name="landing"),
    path("login/", teacher_login, name="teacher_login"),
    path("logout/", teacher_logout, name="teacher_logout"),
    path("dashboard/", teacher_dashboard, name="teacher_dashboard"),
    path("proprietor/", proprietor_dashboard, name="proprietor_dashboard"),
    path("setup/", setup_wizard, name="setup_wizard"),
    path("branding/", branding_settings, name="branding_settings"),
    path("permissions/matrix/", role_permission_matrix, name="role_permission_matrix"),
    path("analytics/export/", analytics_export, name="analytics_export"),
    path("analytics/promotion-export/", promotion_analytics_export, name="promotion_analytics_export"),
    path("notifications/", staff_notifications, name="staff_notifications"),
    path("notifications/read-all/", staff_mark_notifications_read, name="staff_mark_notifications_read"),
    path("notifications/<int:notification_id>/read/", staff_mark_notification_read, name="staff_mark_notification_read"),
    path("parent-email-audit/", parent_email_audit, name="parent_email_audit"),
    path("schedules/", schedule_manager, name="schedule_manager"),
    path("health/", system_health, name="system_health"),
]
