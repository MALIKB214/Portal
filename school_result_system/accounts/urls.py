from django.urls import path
from .views import (
    landing_page,
    teacher_login,
    teacher_logout,
    teacher_dashboard,
    proprietor_dashboard,
    setup_wizard,
    analytics_export,
    branding_settings,
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
    path("analytics/export/", analytics_export, name="analytics_export"),
]
