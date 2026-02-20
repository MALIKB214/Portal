from django import forms

from .models import ContactMessage, SchoolBranding


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["full_name", "email", "phone", "school_name", "message"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "full_name": "Your full name",
            "email": "you@example.com",
            "phone": "Phone number",
            "school_name": "Your school (optional)",
            "message": "Tell us what you need",
        }
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["placeholder"] = placeholders.get(name, "")
        self.fields["message"].widget.attrs["rows"] = 4


class SchoolBrandingForm(forms.ModelForm):
    class Meta:
        model = SchoolBranding
        fields = [
            "school_name",
            "school_motto",
            "school_logo",
            "principal_signature_name",
            "class_teacher_signature_name",
            "grade_a_min",
            "grade_b_min",
            "grade_c_min",
            "grade_d_min",
            "pass_mark",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-control"
            if isinstance(field.widget, forms.ClearableFileInput):
                css_class = "form-control"
            field.widget.attrs["class"] = css_class
