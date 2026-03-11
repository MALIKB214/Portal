from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "results"

urlpatterns = [
    path("check/", views.check_result, name="check_result"),
    path("parent/login/", views.parent_portal_login, name="parent_login"),
    path(
        "parent/password-reset/",
        views.ParentPasswordResetView.as_view(),
        name="parent_password_reset",
    ),
    path(
        "parent/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="results/parent_password_reset_done.html",
        ),
        name="parent_password_reset_done",
    ),
    path(
        "parent/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="results/parent_password_reset_confirm.html",
            success_url="/results/parent/reset/done/",
        ),
        name="parent_password_reset_confirm",
    ),
    path(
        "parent/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="results/parent_password_reset_complete.html",
        ),
        name="parent_password_reset_complete",
    ),
    path("parent/logout/", views.parent_portal_logout, name="parent_logout"),
    path("parent/notifications/", views.parent_notifications, name="parent_notifications"),
    path("parent/notifications/read/", views.parent_mark_notifications_read, name="parent_mark_notifications_read"),
    path("parent/notifications/<int:notification_id>/read/", views.parent_mark_notification_read, name="parent_mark_notification_read"),
    path("parent/dashboard/", views.parent_dashboard, name="parent_dashboard"),
    path("parent/wallet/", views.parent_wallet, name="parent_wallet"),
    path("parent/portal/", views.parent_portal, name="parent_portal"),
    path(
        "download/<int:student_id>/<int:session_id>/<int:term_id>/",
        views.download_result_pdf,
        name="download_result",
    ),
    path("download-all/", views.download_all_results_pdf, name="download_all_results"),
    path("add/", views.add_result, name="add"),
    path("submit/", views.submit_results_for_review, name="submit_for_review"),
    path("", views.result_list, name="list"),
    path("sheet/", views.results_sheet, name="sheet"),
    path("broadsheet/", views.broadsheet, name="broadsheet"),
    path("broadsheet/export/", views.broadsheet_export, name="broadsheet_export"),
    path("release/", views.release_results, name="release_results"),
    path("snapshots/", views.snapshot_verification, name="snapshot_verification"),
    path("student/<int:student_id>/", views.student_results_sheet, name="student_results_sheet"),
]
