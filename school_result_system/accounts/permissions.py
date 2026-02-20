from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render


def is_teacher(user):
    return user.is_authenticated and getattr(user, "is_teacher", False)


def is_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)
    )


def is_proprietor(user):
    return user.is_authenticated and (
        getattr(user, "is_proprietor", False) or is_admin(user)
    )


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
        messages.error(request, "You are not authorized to access billing.")
        return redirect("accounts:teacher_dashboard")

    return _wrapped


def teacher_with_class_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_teacher(request.user):
            messages.error(request, "You are not authorized to access this area.")
            return redirect("accounts:teacher_dashboard")
        if not getattr(request.user, "teacher_class", None):
            return render(request, "accounts/no_class_assigned.html")
        return view_func(request, *args, **kwargs)

    return _wrapped
