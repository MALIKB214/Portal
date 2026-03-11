from django.db import models
from academics.models import AcademicSession, SchoolClass

class Student(models.Model):
    GENDER_CHOICES = (
        ("M", "Male"),
        ("F", "Female"),
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    admission_number = models.CharField(max_length=100, unique=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    class_name = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(blank=True)
    parent_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        last_name = self.last_name or ""
        return f"{self.first_name} {last_name}".strip()

    def save(self, *args, **kwargs):
        if self.school_class and not self.class_name:
            self.class_name = self.school_class.name
        if not self.school_class and self.class_name:
            existing_class = SchoolClass.objects.filter(name=self.class_name).first()
            if existing_class:
                self.school_class = existing_class
        super().save(*args, **kwargs)
