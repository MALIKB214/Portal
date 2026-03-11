from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from academics.models import SchoolClass

class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    is_teacher = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_proprietor = models.BooleanField(default=False)
    is_bursar = models.BooleanField(default=False)
    is_principal = models.BooleanField(default=False)
    teacher_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True
    )
    analytics_chart_stacked = models.BooleanField(default=False)
    analytics_chart_show_legend = models.BooleanField(default=True)


class StaffNotification(models.Model):
    CATEGORY_RESULTS = "results"
    CATEGORY_FINANCE = "finance"
    CATEGORY_ACCOUNT = "account"
    CATEGORY_SYSTEM = "system"
    CATEGORY_CHOICES = (
        (CATEGORY_RESULTS, "Results"),
        (CATEGORY_FINANCE, "Finance"),
        (CATEGORY_ACCOUNT, "Account"),
        (CATEGORY_SYSTEM, "System"),
    )

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_notifications",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SYSTEM,
    )
    message = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "is_read")),
            models.Index(fields=("category", "-created_at")),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.message[:40]}"


class SchoolBranding(models.Model):
    GRADING_TEMPLATE_CUSTOM = "custom"
    GRADING_TEMPLATE_WAEC = "waec"
    GRADING_TEMPLATE_STRICT = "strict"
    GRADING_TEMPLATE_CHOICES = (
        (GRADING_TEMPLATE_CUSTOM, "Custom"),
        (GRADING_TEMPLATE_WAEC, "WAEC Standard"),
        (GRADING_TEMPLATE_STRICT, "Strict Senior"),
    )
    REPORT_STYLE_CLASSIC = "classic"
    REPORT_STYLE_COMPACT = "compact"
    REPORT_STYLE_CHOICES = (
        (REPORT_STYLE_CLASSIC, "Classic"),
        (REPORT_STYLE_COMPACT, "Compact"),
    )
    PRINT_DENSITY_STANDARD = "standard"
    PRINT_DENSITY_DENSE = "dense"
    PRINT_DENSITY_CHOICES = (
        (PRINT_DENSITY_STANDARD, "Standard"),
        (PRINT_DENSITY_DENSE, "High Density"),
    )

    id = models.AutoField(primary_key=True)
    school_name = models.CharField(max_length=150, default="Al-Waarith Model College")
    school_motto = models.CharField(max_length=200, default="Results and Records Portal")
    school_logo = models.FileField(upload_to="branding/", blank=True, null=True)
    principal_signature_name = models.CharField(max_length=120, default="Principal")
    class_teacher_signature_name = models.CharField(max_length=120, default="Class Teacher")
    principal_signature_file = models.FileField(
        upload_to="branding/signatures/", blank=True, null=True
    )
    class_teacher_signature_file = models.FileField(
        upload_to="branding/signatures/", blank=True, null=True
    )
    grading_template = models.CharField(
        max_length=16, choices=GRADING_TEMPLATE_CHOICES, default=GRADING_TEMPLATE_CUSTOM
    )
    report_template_style = models.CharField(
        max_length=16, choices=REPORT_STYLE_CHOICES, default=REPORT_STYLE_CLASSIC
    )
    report_print_density = models.CharField(
        max_length=16, choices=PRINT_DENSITY_CHOICES, default=PRINT_DENSITY_STANDARD
    )
    result_footer_note = models.CharField(max_length=160, blank=True)

    grade_a_min = models.PositiveSmallIntegerField(default=70)
    grade_b_min = models.PositiveSmallIntegerField(default=60)
    grade_c_min = models.PositiveSmallIntegerField(default=50)
    grade_d_min = models.PositiveSmallIntegerField(default=45)
    pass_mark = models.PositiveSmallIntegerField(default=45)
    promotion_min_attendance_rate = models.FloatField(default=75.0)
    promotion_min_behavior_average = models.FloatField(default=2.5)
    promotion_require_non_cognitive = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "School Branding"
        verbose_name_plural = "School Branding"

    def __str__(self):
        return self.school_name

    def clean(self):
        if not (self.grade_a_min >= self.grade_b_min >= self.grade_c_min >= self.grade_d_min >= 0):
            raise ValidationError("Grade boundaries must be descending: A >= B >= C >= D >= 0.")
        if self.grade_a_min > 100:
            raise ValidationError("Grade A minimum cannot be greater than 100.")
        if self.pass_mark > 100:
            raise ValidationError("Pass mark cannot be greater than 100.")
        if self.promotion_min_attendance_rate < 0 or self.promotion_min_attendance_rate > 100:
            raise ValidationError("Promotion attendance rate must be between 0 and 100.")
        if self.promotion_min_behavior_average < 1 or self.promotion_min_behavior_average > 5:
            raise ValidationError("Promotion behavior minimum must be between 1 and 5.")

    @classmethod
    def get_solo(cls):
        obj = cls.objects.order_by("id").first()
        if obj:
            return obj
        return cls.objects.create()


class ContactMessage(models.Model):
    id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    school_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=40, blank=True)
    intended_class = models.CharField(max_length=30, blank=True)
    reason = models.CharField(max_length=60, blank=True)
    preferred_contact = models.CharField(max_length=40, blank=True)
    guardian_name = models.CharField(max_length=120, blank=True)
    student_age = models.PositiveSmallIntegerField(null=True, blank=True)
    preferred_visit_date = models.DateField(null=True, blank=True)
    referral_source = models.CharField(max_length=80, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.full_name} ({self.email})"


class SystemEventLog(models.Model):
    id = models.AutoField(primary_key=True)
    action = models.CharField(max_length=80)
    detail = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action", "-created_at")),
        ]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class RoleCapabilityPolicy(models.Model):
    ROLE_TEACHER = "teacher"
    ROLE_BURSAR = "bursar"
    ROLE_PRINCIPAL = "principal"
    ROLE_PROPRIETOR = "proprietor"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = (
        (ROLE_TEACHER, "Teacher"),
        (ROLE_BURSAR, "Bursar"),
        (ROLE_PRINCIPAL, "Principal"),
        (ROLE_PROPRIETOR, "Proprietor"),
        (ROLE_ADMIN, "Admin"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    capability = models.CharField(max_length=80)
    is_allowed = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("role", "capability")
        ordering = ("role", "capability")
        verbose_name = "Role Capability Policy"
        verbose_name_plural = "Role Capability Policies"

    def __str__(self):
        state = "allow" if self.is_allowed else "deny"
        return f"{self.role}:{self.capability}={state}"
