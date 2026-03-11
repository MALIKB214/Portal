from django import forms

from .models import ContactMessage, SchoolBranding


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = [
            "full_name",
            "email",
            "phone",
            "school_name",
            "role",
            "intended_class",
            "reason",
            "preferred_contact",
            "guardian_name",
            "student_age",
            "preferred_visit_date",
            "referral_source",
            "message",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_choices = [
            ("", "Select role"),
            ("parent", "Parent / Guardian"),
            ("student", "Prospective Student"),
            ("staff", "Staff"),
            ("other", "Other"),
        ]
        reason_choices = [
            ("", "Select reason"),
            ("admissions", "Admissions"),
            ("fees", "Fees / Payments"),
            ("results", "Result Portal"),
            ("general", "General Enquiry"),
        ]
        preferred_choices = [
            ("", "Preferred contact method"),
            ("call", "Call"),
            ("email", "Email"),
            ("whatsapp", "WhatsApp"),
        ]
        if "role" in self.fields:
            self.fields["role"].widget = forms.Select(choices=role_choices)
        if "reason" in self.fields:
            self.fields["reason"].widget = forms.Select(choices=reason_choices)
        if "preferred_contact" in self.fields:
            self.fields["preferred_contact"].widget = forms.Select(choices=preferred_choices)
        if "preferred_visit_date" in self.fields:
            self.fields["preferred_visit_date"].widget = forms.DateInput(
                attrs={"type": "date"}
            )
        placeholders = {
            "full_name": "Your full name",
            "email": "you@example.com",
            "phone": "Phone number",
            "school_name": "Your school (optional)",
            "role": "Parent / Guardian / Student / Staff",
            "intended_class": "JSS1, SS1, Transfer, etc.",
            "reason": "Admissions, Fees, Result portal, Other",
            "preferred_contact": "Call, Email, WhatsApp",
            "guardian_name": "Parent/Guardian full name",
            "student_age": "Student age",
            "preferred_visit_date": "Preferred visit date",
            "referral_source": "Referral / Social media / Friend / Other",
            "message": "Tell us what you need",
        }
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["placeholder"] = placeholders.get(name, "")
        self.fields["message"].widget.attrs["rows"] = 4

    def clean(self):
        cleaned = super().clean()
        reason = (cleaned.get("reason") or "").strip()
        if reason == "admissions":
            required_fields = ["guardian_name", "student_age", "preferred_visit_date"]
            for field_name in required_fields:
                if not cleaned.get(field_name):
                    self.add_error(field_name, "This field is required for admissions enquiries.")
        return cleaned


class SchoolBrandingForm(forms.ModelForm):
    class Meta:
        model = SchoolBranding
        fields = [
            "school_name",
            "school_motto",
            "school_logo",
            "principal_signature_name",
            "class_teacher_signature_name",
            "principal_signature_file",
            "class_teacher_signature_file",
            "grading_template",
            "report_template_style",
            "report_print_density",
            "result_footer_note",
            "grade_a_min",
            "grade_b_min",
            "grade_c_min",
            "grade_d_min",
            "pass_mark",
            "promotion_min_attendance_rate",
            "promotion_min_behavior_average",
            "promotion_require_non_cognitive",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-control"
            if isinstance(field.widget, forms.ClearableFileInput):
                css_class = "form-control"
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"
            field.widget.attrs["class"] = css_class
