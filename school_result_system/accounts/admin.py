from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User,
    SchoolBranding,
    ContactMessage,
    SystemEventLog,
    RoleCapabilityPolicy,
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('is_teacher', 'is_admin', 'is_proprietor', 'is_bursar', 'is_principal', 'teacher_class')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('is_teacher', 'is_admin', 'is_proprietor', 'is_bursar', 'is_principal', 'teacher_class')}),
    )


@admin.register(SchoolBranding)
class SchoolBrandingAdmin(admin.ModelAdmin):
    list_display = (
        "school_name",
        "grading_template",
        "report_template_style",
        "report_print_density",
        "pass_mark",
        "updated_at",
    )


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "role",
        "intended_class",
        "reason",
        "preferred_contact",
        "guardian_name",
        "student_age",
        "preferred_visit_date",
        "referral_source",
        "school_name",
        "created_at",
        "is_resolved",
    )
    list_filter = (
        "is_resolved",
        "created_at",
        "role",
        "reason",
        "preferred_contact",
        "referral_source",
    )
    search_fields = (
        "full_name",
        "email",
        "school_name",
        "message",
        "role",
        "intended_class",
        "reason",
        "preferred_contact",
        "guardian_name",
        "referral_source",
    )
    readonly_fields = ("created_at",)


@admin.register(SystemEventLog)
class SystemEventLogAdmin(admin.ModelAdmin):
    list_display = ("action", "created_by", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("action", "detail")


@admin.register(RoleCapabilityPolicy)
class RoleCapabilityPolicyAdmin(admin.ModelAdmin):
    list_display = ("role", "capability", "is_allowed", "updated_at")
    list_filter = ("role", "is_allowed")
    search_fields = ("capability",)
