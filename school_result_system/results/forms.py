from django import forms
from django.db.models import Q
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model

from academics.models import Term

from .models import ParentPortalAccount, Result, ResultWorkflow, StudentDomainAssessment


class ResultForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = [
            "student",
            "subject",
            "session",
            "term",
            "ca1",
            "ca2",
            "exam",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["session"].required = True
        self.fields["term"].required = True
        select_fields = ["student", "subject", "session", "term"]
        for field in select_fields:
            self.fields[field].widget.attrs["class"] = "form-select mt-1"
        for field in ["ca1", "ca2", "exam"]:
            self.fields[field].widget.attrs["placeholder"] = "0"
            self.fields[field].widget.attrs["class"] = "form-control"
        self.fields["ca1"].widget.attrs["max"] = 20
        self.fields["ca2"].widget.attrs["max"] = 20
        self.fields["exam"].widget.attrs["max"] = 60

        selected_session_id = (
            self.data.get("session")
            or self.initial.get("session")
            or getattr(self.instance, "session_id", None)
        )
        if selected_session_id:
            self.fields["term"].queryset = Term.objects.filter(
                session_id=selected_session_id
            ).order_by("order")
        else:
            self.fields["term"].queryset = Term.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        subject = cleaned_data.get("subject")
        session = cleaned_data.get("session")
        term = cleaned_data.get("term")
        from .models import ResultRelease

        if student and subject and session and term:
            if term.session_id != session.id:
                raise forms.ValidationError("Selected term does not belong to selected session.")

            if self.instance and self.instance.pk and self.instance.status == Result.STATUS_APPROVED:
                raise forms.ValidationError("Approved results cannot be edited.")

            student_class = (student.class_name or "").strip()
            release_exists = ResultRelease.objects.filter(session=session, term=term).filter(
                Q(class_name="") | Q(class_name__iexact=student_class)
            ).exists()
            if release_exists:
                raise forms.ValidationError(
                    "This result is locked because the term has already been approved/released."
                )
            school_class = getattr(student, "school_class", None)
            if school_class:
                workflow = ResultWorkflow.objects.filter(
                    session=session, term=term, school_class=school_class
                ).first()
                if workflow and workflow.status in {
                    ResultWorkflow.STATUS_APPROVED,
                    ResultWorkflow.STATUS_RELEASED,
                }:
                    raise forms.ValidationError(
                        "This result is locked because the class workflow is already approved/released."
                    )

            exists_qs = Result.objects.filter(
                student=student,
                subject=subject,
                session=session,
                term=term,
            )
            if self.instance and self.instance.pk:
                exists_qs = exists_qs.exclude(pk=self.instance.pk)
            exists = exists_qs.exists()

            if exists:
                raise forms.ValidationError(
                    "This student already has a result for this subject in the selected term."
                )

        return cleaned_data

    def save(self, commit=True):
        from .models import ResultAudit

        old_scores = {}
        if self.instance and self.instance.pk:
            previous = Result.objects.get(pk=self.instance.pk)
            old_scores = {
                "ca1": previous.ca1,
                "ca2": previous.ca2,
                "exam": previous.exam,
            }

        result = super().save(commit=False)
        if self.user:
            if not result.pk:
                result.created_by = self.user
            result.updated_by = self.user
        if commit:
            result.save()

        if self.user and old_scores:
            new_scores = {
                "ca1": result.ca1,
                "ca2": result.ca2,
                "exam": result.exam,
            }
            if old_scores != new_scores:
                ResultAudit.objects.create(
                    result=result,
                    changed_by=self.user,
                    old_scores=old_scores,
                    new_scores=new_scores,
                )

        return result


class StudentDomainAssessmentForm(forms.ModelForm):
    class Meta:
        model = StudentDomainAssessment
        fields = [
            "discipline",
            "respect",
            "punctuality",
            "teamwork",
            "leadership",
            "moral_conduct",
            "handwriting",
            "sport",
            "laboratory_practical",
            "technical_drawing",
            "creative_arts",
            "computer_practical",
            "times_school_opened",
            "times_present",
            "times_absent",
            "teacher_remark",
            "principal_remark",
            "next_term_begins",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        score_fields = [
            "discipline",
            "respect",
            "punctuality",
            "teamwork",
            "leadership",
            "moral_conduct",
            "handwriting",
            "sport",
            "laboratory_practical",
            "technical_drawing",
            "creative_arts",
            "computer_practical",
        ]
        for field in score_fields:
            self.fields[field].widget.attrs.update({"class": "form-control", "min": 1, "max": 5})
        attendance_fields = ["times_school_opened", "times_present", "times_absent"]
        for field in attendance_fields:
            self.fields[field].widget.attrs.update(
                {"class": "form-control", "min": 0, "placeholder": "0"}
            )
        self.fields["teacher_remark"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Class teacher remark for the term"}
        )
        self.fields["principal_remark"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Principal remark"}
        )
        self.fields["next_term_begins"].widget.attrs.update(
            {"class": "form-control", "placeholder": "e.g. 15/09/2026"}
        )


class ParentPortalLoginForm(forms.Form):
    username = forms.CharField(required=False)
    password = forms.CharField(required=False, widget=forms.PasswordInput)
    admission_number = forms.CharField(required=False)
    parent_surname = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("username", "password", "admission_number", "parent_surname"):
            self.fields[field_name].widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned = super().clean()
        username = (cleaned.get("username") or "").strip()
        password = (cleaned.get("password") or "").strip()
        admission = (cleaned.get("admission_number") or "").strip()
        surname = (cleaned.get("parent_surname") or "").strip()

        credential_mode = bool(username and password)
        legacy_mode = bool(admission and surname)
        if not credential_mode and not legacy_mode:
            raise forms.ValidationError(
                "Provide parent account username/password, or legacy admission number + surname."
            )
        return cleaned


class ParentPasswordResetForm(PasswordResetForm):
    """
    Restrict parent password reset to active parent portal accounts only.
    """

    def get_users(self, email):
        lookup = (email or "").strip().lower()
        if not lookup:
            return iter(())

        parent_accounts = ParentPortalAccount.objects.filter(is_active=True).select_related(
            "user", "student"
        )
        matched_users = []
        seen_user_ids = set()

        for account in parent_accounts:
            user = account.user
            if not user or not user.is_active or not user.has_usable_password():
                continue
            candidates = {
                (user.email or "").strip().lower(),
                (account.student.parent_email or "").strip().lower(),
                (account.student.email or "").strip().lower(),
            }
            if lookup in candidates and user.id not in seen_user_ids:
                matched_users.append(user)
                seen_user_ids.add(user.id)

        return iter(matched_users)
