
from django.templatetags.static import static

from .models import SchoolBranding
from .capabilities import (
    CAP_ENTER_RESULTS,
    CAP_MANAGE_STUDENTS,
    CAP_RELEASE_RESULTS,
    CAP_VIEW_FINANCE,
    CAP_VIEW_PROPRIETOR_DASHBOARD,
    CAP_VIEW_TEACHER_DASHBOARD,
    has_capability,
)


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
        "accounts:role_permission_matrix": "css/pages/accounts/branding_settings.css",
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
        "results:snapshot_verification": "css/pages/results/release_results.css",
        "results:parent_login": "css/pages/results/check.css",
        "results:parent_dashboard": "css/pages/results/single_student_result.css",
        "results:parent_wallet": "css/pages/results/parent_wallet.css",
        "results:parent_portal": "css/pages/results/single_student_result.css",
        "results:download_result": "css/pages/results/result_detail.css",
        "results:download_all_results": "css/pages/results/results_sheet.css",
        "billing:invoice_list": "css/pages/billing/invoice_list.css",
        "billing:dashboard": "css/pages/billing/invoice_list.css",
        "billing:my_payment_history": "css/pages/billing/invoice_list.css",
        "billing:invoice_create": "css/pages/billing/invoice_create.css",
        "billing:invoice_detail": "css/pages/billing/invoice_detail.css",
        "billing:receipt": "css/pages/billing/receipt.css",
        "billing:reconciliation_report": "css/pages/billing/invoice_list.css",
    }
    return {"page_css_path": css_map.get(view_name, "")}


def school_branding(request):
    try:
        brand = SchoolBranding.get_solo()
        logo_url = brand.school_logo.url if brand.school_logo else static("img/school_badge.svg")
        user = getattr(request, "user", None)
        is_bursar_user = bool(
            user
            and user.is_authenticated
            and (getattr(user, "is_bursar", False) or user.groups.filter(name="Bursar").exists())
        )
        is_principal_user = bool(
            user
            and user.is_authenticated
            and (getattr(user, "is_principal", False) or user.groups.filter(name="Principal").exists())
        )
        can_view_finance_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_VIEW_FINANCE)
        )
        can_view_teacher_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_VIEW_TEACHER_DASHBOARD)
        )
        can_manage_students_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_MANAGE_STUDENTS)
        )
        can_enter_results_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_ENTER_RESULTS)
        )
        can_view_proprietor_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_VIEW_PROPRIETOR_DASHBOARD)
        )
        can_release_results_menu = bool(
            user
            and user.is_authenticated
            and has_capability(user, CAP_RELEASE_RESULTS)
        )
        return {
            "school_branding": brand,
            "school_name_display": brand.school_name,
            "school_motto_display": brand.school_motto,
            "school_logo_url": logo_url,
            "is_bursar_user": is_bursar_user,
            "is_principal_user": is_principal_user,
            "can_view_finance_menu": can_view_finance_menu,
            "can_view_teacher_menu": can_view_teacher_menu,
            "can_manage_students_menu": can_manage_students_menu,
            "can_enter_results_menu": can_enter_results_menu,
            "can_view_proprietor_menu": can_view_proprietor_menu,
            "can_release_results_menu": can_release_results_menu,
        }
    except Exception:
        return {
            "school_branding": None,
            "school_name_display": "Al-Waarith Model College",
            "school_motto_display": "Results and Records Portal",
            "school_logo_url": static("img/school_badge.svg"),
            "is_bursar_user": False,
            "is_principal_user": False,
            "can_view_finance_menu": False,
            "can_view_teacher_menu": False,
            "can_manage_students_menu": False,
            "can_enter_results_menu": False,
            "can_view_proprietor_menu": False,
            "can_release_results_menu": False,
        }
