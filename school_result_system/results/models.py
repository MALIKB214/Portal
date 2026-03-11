from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from students.models import Student
from academics.models import Subject, AcademicSession, Term, SchoolClass
from .grading import grade_from_score


class Result(models.Model):
    id = models.AutoField(primary_key=True)
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
        indexes = [
            models.Index(fields=("session", "term", "student")),
            models.Index(fields=("session", "student")),
            models.Index(fields=("status", "session", "term")),
        ]

    def clean(self):
        errors = {}
        for field, max_score in (("ca1", 20), ("ca2", 20), ("exam", 60)):
            value = getattr(self, field)
            if value is None:
                continue
            if value < 0 or value > max_score:
                errors[field] = f"{field.upper()} must be between 0 and {max_score}."

        if self.total_score > 100:
            errors["exam"] = "Total score cannot exceed 100."

        if self.session and self.term and self.term.session_id != self.session_id:
            errors["term"] = "Selected term does not belong to selected session."

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
                score_fields = ("ca1", "ca2", "exam")
                score_changed = any(
                    getattr(previous, field) != getattr(self, field)
                    for field in score_fields
                )
                if score_changed:
                    errors["status"] = "Approved results cannot be edited."

        if self.session and self.term and self.student:
            student_class = (self.student.class_name or "").strip()
            release_exists = ResultRelease.objects.filter(
                session=self.session,
                term=self.term,
            ).filter(Q(class_name="") | Q(class_name__iexact=student_class)).exists()
            if release_exists:
                errors["term"] = "This term is locked because results were approved/released."
            if self.student.school_class_id:
                workflow = ResultWorkflow.objects.filter(
                    session=self.session,
                    term=self.term,
                    school_class_id=self.student.school_class_id,
                ).first()
                if workflow and workflow.status in {
                    ResultWorkflow.STATUS_APPROVED,
                    ResultWorkflow.STATUS_RELEASED,
                }:
                    errors["status"] = "Class workflow is locked after approval/release."

        if errors:
            raise ValidationError(errors)

    @property
    def total_score(self):
        return self.ca1 + self.ca2 + self.exam

    def grade(self):
        return grade_from_score(self.total_score)


class ResultAudit(models.Model):
    id = models.AutoField(primary_key=True)
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
    id = models.AutoField(primary_key=True)
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


class ResultWorkflow(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_RELEASED = "released"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_RELEASED, "Released"),
    )

    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflows_submitted",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflows_approved",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflows_released",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("session", "term", "school_class")
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.session} - {self.term} - {self.school_class} ({self.status})"


class ResultSnapshot(models.Model):
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    workflow = models.ForeignKey(
        ResultWorkflow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="result_snapshots_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64)
    signature = models.CharField(max_length=64)
    verified_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="result_snapshots_invalidated",
    )
    invalidation_reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("session", "term", "school_class")
        ordering = ("school_class__name",)
        indexes = [
            models.Index(fields=("session", "term", "school_class")),
            models.Index(fields=("invalidated_at",)),
        ]

    def __str__(self):
        status = "invalidated" if self.invalidated_at else "active"
        return f"{self.session} - {self.term} - {self.school_class} ({status})"


class ResultReopenLog(models.Model):
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=240, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    reopened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-reopened_at",)
        indexes = [
            models.Index(fields=("session", "term", "school_class")),
        ]


class Notification(models.Model):
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
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="notifications")
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, null=True, blank=True)
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
            models.Index(fields=("student", "is_read")),
            models.Index(fields=("session", "term")),
            models.Index(fields=("-created_at",)),
        ]


class ParentPortalAccount(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_portal_account",
    )
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_portal_account",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.username} -> {self.student.full_name}"


class StudentDomainAssessment(models.Model):
    id = models.AutoField(primary_key=True)
    SCORE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="domain_assessments")
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="domain_assessments_filled",
    )
    discipline = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    respect = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    punctuality = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    teamwork = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    leadership = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    moral_conduct = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    handwriting = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    sport = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    laboratory_practical = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    technical_drawing = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    creative_arts = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    computer_practical = models.PositiveSmallIntegerField(default=3, validators=SCORE_VALIDATORS)
    times_school_opened = models.PositiveSmallIntegerField(default=0)
    times_present = models.PositiveSmallIntegerField(default=0)
    times_absent = models.PositiveSmallIntegerField(default=0)
    teacher_remark = models.CharField(max_length=200, blank=True)
    principal_remark = models.CharField(max_length=220, blank=True)
    next_term_begins = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "session", "term")
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.student.full_name} - {self.session} - {self.term}"

    @property
    def affective_average(self):
        scores = [
            self.discipline,
            self.respect,
            self.punctuality,
            self.teamwork,
            self.leadership,
            self.moral_conduct,
        ]
        return round(sum(scores) / len(scores), 2)

    @property
    def psychomotor_average(self):
        scores = [
            self.handwriting,
            self.sport,
            self.laboratory_practical,
            self.technical_drawing,
            self.creative_arts,
            self.computer_practical,
        ]
        return round(sum(scores) / len(scores), 2)
