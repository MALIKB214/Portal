from functools import lru_cache

from django.apps import apps
from django.db.utils import OperationalError, ProgrammingError

CAP_VIEW_TEACHER_DASHBOARD = "teacher.dashboard.view"
CAP_MANAGE_STUDENTS = "students.manage"
CAP_ENTER_RESULTS = "results.enter"
CAP_SUBMIT_RESULTS = "results.submit"
CAP_APPROVE_RESULTS = "results.approve"
CAP_RELEASE_RESULTS = "results.release"
CAP_VIEW_PROPRIETOR_DASHBOARD = "proprietor.dashboard.view"
CAP_VIEW_FINANCE = "finance.view"
CAP_RECORD_FINANCE = "finance.record"
CAP_APPROVE_FINANCE = "finance.approve"
CAP_REVERSE_FINANCE = "finance.reverse"
CAP_VOID_INVOICE = "finance.void_invoice"
CAP_VIEW_ANALYTICS_EXPORT = "analytics.export"

ALL_CAPABILITIES = (
    CAP_VIEW_TEACHER_DASHBOARD,
    CAP_MANAGE_STUDENTS,
    CAP_ENTER_RESULTS,
    CAP_SUBMIT_RESULTS,
    CAP_APPROVE_RESULTS,
    CAP_RELEASE_RESULTS,
    CAP_VIEW_PROPRIETOR_DASHBOARD,
    CAP_VIEW_FINANCE,
    CAP_RECORD_FINANCE,
    CAP_APPROVE_FINANCE,
    CAP_REVERSE_FINANCE,
    CAP_VOID_INVOICE,
    CAP_VIEW_ANALYTICS_EXPORT,
)

MANAGED_ROLES = ("teacher", "bursar", "principal", "proprietor", "admin")


ROLE_CAPABILITIES = {
    "teacher": {
        CAP_VIEW_TEACHER_DASHBOARD,
        CAP_MANAGE_STUDENTS,
        CAP_ENTER_RESULTS,
        CAP_SUBMIT_RESULTS,
    },
    "bursar": {
        CAP_VIEW_FINANCE,
        CAP_RECORD_FINANCE,
    },
    "principal": {
        CAP_VIEW_FINANCE,
        CAP_APPROVE_FINANCE,
    },
    "proprietor": {
        CAP_VIEW_PROPRIETOR_DASHBOARD,
        CAP_APPROVE_RESULTS,
        CAP_RELEASE_RESULTS,
        CAP_VIEW_FINANCE,
        CAP_RECORD_FINANCE,
        CAP_APPROVE_FINANCE,
        CAP_REVERSE_FINANCE,
        CAP_VOID_INVOICE,
        CAP_VIEW_ANALYTICS_EXPORT,
    },
    "admin": {
        CAP_VIEW_PROPRIETOR_DASHBOARD,
        CAP_APPROVE_RESULTS,
        CAP_RELEASE_RESULTS,
        CAP_VIEW_FINANCE,
        CAP_RECORD_FINANCE,
        CAP_APPROVE_FINANCE,
        CAP_REVERSE_FINANCE,
        CAP_VOID_INVOICE,
        CAP_VIEW_ANALYTICS_EXPORT,
    },
}


def _user_roles(user):
    roles = set()
    if not user or not user.is_authenticated:
        return roles

    if getattr(user, "is_superuser", False):
        roles.add("admin")
    if getattr(user, "is_admin", False):
        roles.add("admin")
    if getattr(user, "is_proprietor", False):
        roles.add("proprietor")
    if getattr(user, "is_teacher", False):
        roles.add("teacher")
    if getattr(user, "is_bursar", False):
        roles.add("bursar")
    if getattr(user, "is_principal", False):
        roles.add("principal")

    user_group_names = set(user.groups.values_list("name", flat=True))
    if "Bursar" in user_group_names:
        roles.add("bursar")
    if "Principal" in user_group_names:
        roles.add("principal")
    return roles


def capabilities_for_user(user):
    roles = _user_roles(user)
    caps = set()
    overrides = get_role_capability_overrides()
    for role in roles:
        caps.update(ROLE_CAPABILITIES.get(role, set()))
        role_overrides = overrides.get(role, {})
        for capability, is_allowed in role_overrides.items():
            if is_allowed:
                caps.add(capability)
            else:
                caps.discard(capability)
    return caps


def has_capability(user, capability):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return capability in capabilities_for_user(user)


@lru_cache(maxsize=1)
def get_role_capability_overrides():
    try:
        policy_model = apps.get_model("accounts", "RoleCapabilityPolicy")
    except LookupError:
        return {}

    try:
        rows = policy_model.objects.all().values("role", "capability", "is_allowed")
    except (ProgrammingError, OperationalError):
        return {}

    overrides = {}
    for row in rows:
        role = row["role"]
        if role not in MANAGED_ROLES or row["capability"] not in ALL_CAPABILITIES:
            continue
        overrides.setdefault(role, {})[row["capability"]] = bool(row["is_allowed"])
    return overrides


def clear_capability_cache():
    get_role_capability_overrides.cache_clear()
