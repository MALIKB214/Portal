
from django.templatetags.static import static

from .models import SchoolBranding


def page_css(request):
    if not request or not hasattr(request, "resolver_match") or not request.resolver_match:
        return {"page_css_path": ""}

    view_name = request.resolver_match.view_name or ""
    css_map = {
        "home": "css/pages/accounts/landing.css",
        "accounts:teacher_dashboard": "css/pages/accounts/teacher_dashboard.css",
        "accounts:proprietor_dashboard": "css/pages/accounts/proprietor_dashboard.css",
        "accounts:landing": "css/pages/accounts/landing.css",
        "accounts:branding_settings": "css/pages/accounts/branding_settings.css",
        "accounts:setup_wizard": "css/pages/accounts/setup_wizard.css",
        "accounts:teacher_login": "css/pages/accounts/login.css",
        "accounts:no_class_assigned": "css/pages/accounts/no_class_assigned.css",
        "students:list": "css/pages/students/student_list.css",
        "students:add": "css/pages/students/student_form.css",
        "students:edit": "css/pages/students/student_form.css",
        "results:add": "css/pages/results/add_result.css",
        "results:sheet": "css/pages/results/results_sheet.css",
        "results:check_result": "css/pages/results/check.css",
        "results:list": "css/pages/results/result_list.css",
        "results:student_results_sheet": "css/pages/results/student_results_sheet.css",
        "results:broadsheet": "css/pages/results/broadsheet.css",
        "results:release_results": "css/pages/results/release_results.css",
        "results:parent_login": "css/pages/results/check.css",
        "results:parent_portal": "css/pages/results/single_student_result.css",
        "results:download_result": "css/pages/results/result_detail.css",
        "results:download_all_results": "css/pages/results/results_sheet.css",
        "billing:invoice_list": "css/pages/billing/invoice_list.css",
        "billing:invoice_create": "css/pages/billing/invoice_create.css",
        "billing:invoice_detail": "css/pages/billing/invoice_detail.css",
        "billing:receipt": "css/pages/billing/receipt.css",
    }
    return {"page_css_path": css_map.get(view_name, "")}


def school_branding(request):
    try:
        brand = SchoolBranding.get_solo()
        logo_url = brand.school_logo.url if brand.school_logo else static("img/school_badge.svg")
        return {
            "school_branding": brand,
            "school_name_display": brand.school_name,
            "school_motto_display": brand.school_motto,
            "school_logo_url": logo_url,
        }
    except Exception:
        return {
            "school_branding": None,
            "school_name_display": "Al-Waarith Model College",
            "school_motto_display": "Results and Records Portal",
            "school_logo_url": static("img/school_badge.svg"),
        }
