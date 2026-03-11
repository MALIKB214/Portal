"""
URL configuration for school_result_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from accounts.views import landing_page
from .views import health_live, health_ready

urlpatterns = [
    path("", landing_page, name="home"),
    path("favicon.ico", RedirectView.as_view(url="/static/img/school_badge.svg", permanent=False)),
    path("result/", RedirectView.as_view(url="/results/", permanent=False)),
    path("health/live/", health_live, name="health_live"),
    path("health/ready/", health_ready, name="health_ready"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("results/", include("results.urls")),
    path("students/", include("students.urls")),
    path("billing/", include("billing.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG or getattr(settings, "SERVE_STATIC", False) or getattr(settings, "FORCE_HTTP", False):
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "school_result_system.views.handler403"
handler404 = "school_result_system.views.handler404"
handler500 = "school_result_system.views.handler500"
