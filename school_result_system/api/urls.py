from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import StudentViewSet, ResultViewSet, AnalyticsView

router = DefaultRouter()
router.register(r"students", StudentViewSet, basename="students")
router.register(r"results", ResultViewSet, basename="results")

urlpatterns = [
    path("", include(router.urls)),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
]
