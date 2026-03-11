from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "first_name",
            "last_name",
            "admission_number",
            "gender",
            "school_class",
            "class_name",
            "email",
            "parent_email",
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["first_name"].widget.attrs["placeholder"] = "e.g. Amina"
        self.fields["last_name"].widget.attrs["placeholder"] = "e.g. Okafor"
        self.fields["admission_number"].widget.attrs["placeholder"] = "e.g. SCH/2026/001"
        self.fields["school_class"].widget.attrs["class"] = "form-select"
        self.fields["class_name"].widget.attrs["placeholder"] = "Auto-filled from class"
        self.fields["email"].widget.attrs["placeholder"] = "student@example.com"
        self.fields["parent_email"].widget.attrs["placeholder"] = "parent@example.com"
        self.fields["class_name"].required = False

        if user and getattr(user, "teacher_class", None):
            self.fields["school_class"].initial = user.teacher_class
            self.fields["school_class"].queryset = self.fields["school_class"].queryset.filter(
                id=user.teacher_class.id
            )
            self.fields["class_name"].initial = user.teacher_class.name
            self.fields["class_name"].widget = forms.HiddenInput()
