from django.urls import path
from . import views

app_name = "results"

urlpatterns = [
    path("check/", views.check_result, name="check_result"),
    path("parent/login/", views.parent_portal_login, name="parent_login"),
    path("parent/logout/", views.parent_portal_logout, name="parent_logout"),
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
    path("student/<int:student_id>/", views.student_results_sheet, name="student_results_sheet"),
]
