from django import forms
from .models import Result


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
            "ca3",
            "project",
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
        for field in ["ca1", "ca2", "ca3", "project", "exam"]:
            self.fields[field].widget.attrs["placeholder"] = "0"
            self.fields[field].widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        subject = cleaned_data.get("subject")
        session = cleaned_data.get("session")
        term = cleaned_data.get("term")
        from .models import ResultRelease

        if student and subject and session and term:
            if self.instance and self.instance.pk and self.instance.status == Result.STATUS_APPROVED:
                raise forms.ValidationError("Approved results cannot be edited.")

            release_exists = ResultRelease.objects.filter(
                session=session,
                term=term,
                class_name__in=["", student.class_name or ""],
            ).exists()
            if release_exists:
                raise forms.ValidationError(
                    "This result is locked because the term has already been approved/released."
                )

            exists = Result.objects.filter(
                student=student,
                subject=subject,
                session=session,
                term=term,
            ).exists()

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
                "ca3": previous.ca3,
                "project": previous.project,
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
                "ca3": result.ca3,
                "project": result.project,
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
