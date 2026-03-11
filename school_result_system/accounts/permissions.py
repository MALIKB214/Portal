from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render
from .capabilities import (
    CAP_APPROVE_FINANCE,
    CAP_RECORD_FINANCE,
    CAP_VIEW_FINANCE,
    CAP_VIEW_PROPRIETOR_DASHBOARD,
    CAP_VIEW_TEACHER_DASHBOARD,
    has_capability,
)


def is_teacher(user):
    return has_capability(user, CAP_VIEW_TEACHER_DASHBOARD)


def is_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)
    )


def is_proprietor(user):
    return has_capability(user, CAP_VIEW_PROPRIETOR_DASHBOARD)


def is_principal(user):
    return has_capability(user, CAP_APPROVE_FINANCE)


def is_bursar(user):
    return has_capability(user, CAP_RECORD_FINANCE)


def can_monitor_finance(user):
    return has_capability(user, CAP_VIEW_FINANCE)


def can_access_staff_portal(user):
    return user.is_authenticated and (
        is_teacher(user) or is_proprietor(user) or is_bursar(user) or is_principal(user)
    )


def default_dashboard_url(user):
    if not user or not user.is_authenticated:
        return "accounts:teacher_login"
    if is_proprietor(user) or is_admin(user):
        return "accounts:proprietor_dashboard"
    if is_bursar(user) or is_principal(user):
        return "billing:dashboard"
    if is_teacher(user):
        return "accounts:teacher_dashboard"
    return "home"


def teacher_required(view_func):
    return login_required(user_passes_test(is_teacher)(view_func))


def admin_required(view_func):
    return login_required(user_passes_test(is_admin)(view_func))


def proprietor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if is_proprietor(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "You are not authorized to access this area.")
        return redirect(default_dashboard_url(request.user))

    return _wrapped


def finance_monitor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if can_monitor_finance(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "You are not authorized to access finance.")
        return redirect(default_dashboard_url(request.user))

    return _wrapped


def bursar_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if is_bursar(request.user) or is_proprietor(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Only bursar can perform this financial action.")
        return redirect(default_dashboard_url(request.user))

    return _wrapped


def teacher_with_class_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_teacher(request.user):
            messages.error(request, "You are not authorized to access this area.")
            return redirect(default_dashboard_url(request.user))
        if not getattr(request.user, "teacher_class", None):
            return render(request, "accounts/no_class_assigned.html")
        return view_func(request, *args, **kwargs)

    return _wrapped


def capability_required(capability):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if has_capability(request.user, capability):
                return view_func(request, *args, **kwargs)
            messages.error(request, "You are not authorized to perform this action.")
            return redirect(default_dashboard_url(request.user))

        return _wrapped

    return decorator


def any_capability_required(*capabilities):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if any(has_capability(request.user, cap) for cap in capabilities):
                return view_func(request, *args, **kwargs)
            messages.error(request, "You are not authorized to perform this action.")
            return redirect(default_dashboard_url(request.user))

        return _wrapped

    return decorator
