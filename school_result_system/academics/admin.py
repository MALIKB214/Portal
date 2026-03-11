from django.contrib import admin
from .models import AcademicSession, SchoolClass, Subject, Term


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name")
    search_fields = ("name", "short_name")


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("session", "order", "name", "is_active")
    list_filter = ("session", "order", "is_active")

