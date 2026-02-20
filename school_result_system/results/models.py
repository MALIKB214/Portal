from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from students.models import Student
from academics.models import Subject, AcademicSession, Term
from .grading import grade_from_score


class Result(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_updated",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_submitted",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_approved",
    )

    ca1 = models.PositiveSmallIntegerField(default=0)
    ca2 = models.PositiveSmallIntegerField(default=0)
    ca3 = models.PositiveSmallIntegerField(default=0)
    project = models.PositiveSmallIntegerField(default=0)
    exam = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    class Meta:
        unique_together = ("student", "subject", "session", "term")
        ordering = ("student", "subject")

    def clean(self):
        errors = {}
        for field, max_score in (
            ("ca1", 10),
            ("ca2", 10),
            ("ca3", 10),
            ("project", 10),
            ("exam", 60),
        ):
            value = getattr(self, field)
            if value is None:
                continue
            if value < 0 or value > max_score:
                errors[field] = f"{field.upper()} must be between 0 and {max_score}."

        if self.total_score > 100:
            errors["exam"] = "Total score cannot exceed 100."

        if self.status == self.STATUS_APPROVED:
            if not self.approved_by:
                errors["status"] = "Approved results must include an approver."
            else:
                can_approve = (
                    getattr(self.approved_by, "is_proprietor", False)
                    or getattr(self.approved_by, "is_admin", False)
                    or getattr(self.approved_by, "is_superuser", False)
                )
                if not can_approve:
                    errors["status"] = "Only proprietor/admin can approve results."
            if not self.approved_at:
                errors["status"] = "Approved results must include approval time."

        if self.pk:
            previous = Result.objects.filter(pk=self.pk).first()
            if previous and previous.status == self.STATUS_APPROVED:
                score_fields = ("ca1", "ca2", "ca3", "project", "exam")
                score_changed = any(
                    getattr(previous, field) != getattr(self, field)
                    for field in score_fields
                )
                if score_changed:
                    errors["status"] = "Approved results cannot be edited."

        if self.session and self.term and self.student:
            release_exists = ResultRelease.objects.filter(
                session=self.session,
                term=self.term,
                class_name__in=["", self.student.class_name or ""],
            ).exists()
            if release_exists:
                errors["term"] = "This term is locked because results were approved/released."

        if errors:
            raise ValidationError(errors)

    @property
    def total_score(self):
        return self.ca1 + self.ca2 + self.ca3 + self.project + self.exam

    def grade(self):
        return grade_from_score(self.total_score)


class ResultAudit(models.Model):
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name="audits")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    old_scores = models.JSONField(default=dict, blank=True)
    new_scores = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-changed_at",)


class ResultRelease(models.Model):
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    released_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "term", "class_name")
        ordering = ("-released_at",)


class Notification(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="notifications")
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, null=True, blank=True)
    message = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
