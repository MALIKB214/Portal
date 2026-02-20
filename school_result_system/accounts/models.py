from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from academics.models import SchoolClass

class User(AbstractUser):
    is_teacher = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_proprietor = models.BooleanField(default=False)
    teacher_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True
    )
    analytics_chart_stacked = models.BooleanField(default=False)
    analytics_chart_show_legend = models.BooleanField(default=True)


class SchoolBranding(models.Model):
    school_name = models.CharField(max_length=150, default="Al-Waarith Model College")
    school_motto = models.CharField(max_length=200, default="Results and Records Portal")
    school_logo = models.FileField(upload_to="branding/", blank=True, null=True)
    principal_signature_name = models.CharField(max_length=120, default="Principal")
    class_teacher_signature_name = models.CharField(max_length=120, default="Class Teacher")

    grade_a_min = models.PositiveSmallIntegerField(default=70)
    grade_b_min = models.PositiveSmallIntegerField(default=60)
    grade_c_min = models.PositiveSmallIntegerField(default=50)
    grade_d_min = models.PositiveSmallIntegerField(default=45)
    pass_mark = models.PositiveSmallIntegerField(default=45)

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

    @classmethod
    def get_solo(cls):
        obj = cls.objects.order_by("id").first()
        if obj:
            return obj
        return cls.objects.create()


class ContactMessage(models.Model):
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    school_name = models.CharField(max_length=150, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.full_name} ({self.email})"
