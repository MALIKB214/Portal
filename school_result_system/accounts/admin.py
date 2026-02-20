from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SchoolBranding, ContactMessage

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('is_teacher', 'is_admin', 'is_proprietor', 'teacher_class')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('is_teacher', 'is_admin', 'is_proprietor', 'teacher_class')}),
    )


@admin.register(SchoolBranding)
class SchoolBrandingAdmin(admin.ModelAdmin):
    list_display = ("school_name", "pass_mark", "updated_at")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "school_name", "created_at", "is_resolved")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("full_name", "email", "school_name", "message")
