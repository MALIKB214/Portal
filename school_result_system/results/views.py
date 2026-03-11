from collections import defaultdict

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from academics.models import AcademicSession, Term, Subject, SchoolClass
from students.models import Student
from .models import (
    Result,
    ResultSnapshot,
    ResultRelease,
    Notification,
    ParentPortalAccount,
    StudentDomainAssessment,
    ResultWorkflow,
)
from .workflow_service import (
    approve_results as approve_results_workflow,
    reopen_results as reopen_results_workflow,
    release_results as release_results_workflow,
    submit_results_for_class,
    _classes_from_results,
    _scoped_students,
)
from .utils import generate_result_pdf, generate_all_results_pdf, generate_broadsheet_pdf
from .forms import ParentPortalLoginForm, ResultForm, StudentDomainAssessmentForm
from .forms import ParentPasswordResetForm
from .notifications import (
    format_parent_login_email,
    format_result_release_email,
    format_teacher_result_approved_email,
    format_teacher_result_released_email,
    notify_parent_event,
    send_parent_email,
    send_teacher_emails_for_class,
)
from .services import (
    compute_pass_fail,
    compute_rankings,
    compute_student_session_snapshot,
    compute_session_cumulative,
    compute_term_totals,
    ordinal as ordinal_rank,
    total_score_expression,
)
from .snapshot_service import verify_snapshot
from accounts.permissions import (
    teacher_required,
    teacher_with_class_required,
    proprietor_required,
    capability_required,
    any_capability_required,
)
from accounts.notifications import create_staff_notification
from accounts.models import User, StaffNotification
from accounts.capabilities import (
    CAP_ENTER_RESULTS,
    CAP_SUBMIT_RESULTS,
    CAP_APPROVE_RESULTS,
    CAP_RELEASE_RESULTS,
    CAP_VIEW_PROPRIETOR_DASHBOARD,
    CAP_VIEW_TEACHER_DASHBOARD,
    has_capability,
)


class ParentPasswordResetView(auth_views.PasswordResetView):
    template_name = "results/parent_password_reset.html"
    email_template_name = "results/emails/parent_password_reset_email.txt"
    success_url = "/results/parent/password-reset/done/"
    form_class = ParentPasswordResetForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email_backend_name"] = getattr(
            settings, "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
        )
        return context

def build_broadsheet_data(session, term):
    students = list(Student.objects.all().order_by("last_name", "first_name"))
    subjects = list(Subject.objects.all().order_by("name"))
    student_ids = [student.id for student in students]

    results = (
        Result.objects.filter(session=session, term=term, student_id__in=student_ids)
        .select_related("student", "subject")
    )

    result_map = defaultdict(dict)
    for result in results:
        result_map[result.student_id][result.subject_id] = result

    students_data = []
    for student in students:
        subject_data = {}
        total_score = 0
        count = 0
        student_results = result_map.get(student.id, {})
        for subject in subjects:
            result = student_results.get(subject.id)
            if result:
                subject_data[subject.id] = result.total_score
                total_score += result.total_score
                count += 1
            else:
                subject_data[subject.id] = ""
        average = round(total_score / count, 2) if count else 0
        students_data.append(
            {
                "student": student,
                "subjects": subject_data,
                "total": total_score,
                "average": average,
            }
        )

    rank_students(students_data)

    subject_averages = {
        row["subject_id"]: round(row["avg"] or 0, 2)
        for row in Result.objects.filter(session=session, term=term)
        .values("subject_id")
        .annotate(avg=Avg(total_score_expression()))
    }

    return students_data, subjects, subject_averages

def get_active_session():
    return (
        AcademicSession.objects.filter(is_active=True).first()
        or AcademicSession.objects.order_by("-id").first()
    )


def get_active_term(session):
    if not session:
        return None
    return (
        Term.objects.filter(session=session, is_active=True).first()
        or Term.objects.filter(session=session).order_by("order").first()
    )


def rank_students(rows, total_key="total"):
    ranked = compute_rankings(rows, total_key=total_key, ranking_policy="competition")
    rows[:] = ranked
    return rows


def ordinal(value):
    return ordinal_rank(value)


def normalize_class_name(value):
    return " ".join((value or "").strip().split())


def get_teacher_students(user):
    if getattr(user, "teacher_class", None):
        return Student.objects.filter(
            Q(school_class=user.teacher_class)
            | Q(school_class__isnull=True, class_name=user.teacher_class.name)
        )
    return Student.objects.none()


def resolve_student_class(student):
    if getattr(student, "school_class", None):
        return student.school_class
    class_name = normalize_class_name(student.class_name)
    if not class_name:
        return None
    from academics.models import SchoolClass
    return SchoolClass.objects.filter(name__iexact=class_name).first()


def get_or_create_workflow(session, term, school_class):
    workflow, _ = ResultWorkflow.objects.get_or_create(
        session=session,
        term=term,
        school_class=school_class,
        defaults={"status": ResultWorkflow.STATUS_DRAFT},
    )
    return workflow

def build_term_totals_map(session, term, students_qs):
    if not (session and term and students_qs.exists()):
        return {}
    student_ids = list(students_qs.values_list("id", flat=True))
    totals = compute_term_totals(session, term, student_ids)
    return {sid: payload["total"] for sid, payload in totals.items()}


def build_session_totals_map(session, students_qs):
    if not (session and students_qs.exists()):
        return {}
    student_ids = list(students_qs.values_list("id", flat=True))
    totals = compute_session_cumulative(session, student_ids)
    return {sid: payload["cumulative_total"] for sid, payload in totals.items()}

def build_term_totals_map_for_ids(session, term, student_ids):
    if not (session and term and student_ids):
        return {}
    totals = compute_term_totals(session, term, student_ids)
    return {sid: payload["total"] for sid, payload in totals.items()}


def build_session_totals_map_for_ids(session, student_ids):
    if not (session and student_ids):
        return {}
    totals = compute_session_cumulative(session, student_ids)
    return {sid: payload["cumulative_total"] for sid, payload in totals.items()}


@proprietor_required
def broadsheet(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    students_data, subjects, subject_averages = build_broadsheet_data(session, term)

    context = {
        "students_data": students_data,
        "subjects": subjects,
        "subject_averages": subject_averages,
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
    }
    return render(request, "results/broadsheet.html", context)


@proprietor_required
def broadsheet_export(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    if not (session and term):
        return render(
            request,
            "results/broadsheet.html",
            {"error": "Session and term required for export."},
        )

    students_data, subjects, subject_averages = build_broadsheet_data(session, term)
    density = (request.GET.get("density") or "").strip().lower()
    if density not in {"standard", "dense"}:
        density = None

    export_type = request.GET.get("export", "csv")
    if export_type == "csv":
        filename = f"broadsheet_{session}_{term}.csv".replace(" ", "_")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        header = ["Student"] + [s.name for s in subjects] + ["Total", "Average", "Position"]
        response.write(",".join(header) + "\n")
        for row in students_data:
            values = [row["student"].full_name]
            for subject in subjects:
                values.append(str(row["subjects"].get(subject.id, "")))
            values += [str(row["total"]), str(row["average"]), str(row["rank_display"])]
            response.write(",".join(values) + "\n")
        response.write("Class Avg," + ",".join([str(subject_averages.get(s.id, "")) for s in subjects]) + ",,,\n")
        return response

    return generate_broadsheet_pdf(
        title="Class Broadsheet",
        session=session,
        term=term,
        subjects=subjects,
        students_data=students_data,
        subject_averages=subject_averages,
        density_override=density,
    )


@any_capability_required(CAP_APPROVE_RESULTS, CAP_RELEASE_RESULTS)
def release_results(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    session = get_active_session()
    term = get_active_term(session)
    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    class_names = list(SchoolClass.objects.order_by("name").values_list("name", flat=True))
    if not class_names:
        class_names = list(
            Student.objects.exclude(class_name__isnull=True)
            .exclude(class_name="")
            .order_by("class_name")
            .values_list("class_name", flat=True)
            .distinct()
        )
    class_name_lookup = {
        normalize_class_name(name).lower(): name for name in class_names
    }

    if request.method == "POST":
        action = request.POST.get("action", "release")
        action = action if action in RELEASE_ACTION_CAPABILITY_MAP else "release"
        required_capability = RELEASE_ACTION_CAPABILITY_MAP[action]
        session_id = request.POST.get("session")
        term_id = request.POST.get("term")
        class_name = normalize_class_name(request.POST.get("class_name"))
        session = AcademicSession.objects.filter(id=session_id).first()
        term = Term.objects.filter(id=term_id, session=session).first()

        if not session or not term:
            messages.error(request, "Session and term are required.")
        elif class_name and class_name.lower() not in class_name_lookup:
            messages.error(request, "Selected class does not exist.")
        else:
            if class_name:
                class_name = class_name_lookup[class_name.lower()]
            scoped_results = _scoped_results(session, term, class_name)
            if not has_capability(request.user, required_capability):
                action_error = "You are not authorized for this action."
                if action == "approve":
                    action_error = "You are not authorized to approve results."
                elif action == "release":
                    action_error = "You are not authorized to release results."
                elif action == "reopen":
                    action_error = "You are not authorized to reopen results."
                messages.error(request, action_error)
                return redirect("results:release_results")

            if action == "approve":
                school_class = None
                if class_name:
                    school_class = SchoolClass.objects.filter(name__iexact=class_name).first()
                    if not school_class:
                        school_class, _ = SchoolClass.objects.get_or_create(name=class_name)
                try:
                    updated = approve_results_workflow(session, term, request.user, school_class=school_class)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("results:release_results")
                if updated:
                    target_classes = [school_class] if school_class else _classes_from_results(scoped_results)
                    approver_name = request.user.get_full_name() or request.user.username
                    for cls in target_classes:
                        subject, body = format_teacher_result_approved_email(
                            cls, term, session, approver_name=approver_name
                        )
                        send_teacher_emails_for_class(subject, body, cls)
                        teachers = User.objects.filter(is_teacher=True, teacher_class=cls)
                        for teacher in teachers:
                            create_staff_notification(
                                teacher,
                                f"Results approved for {cls} - {term} ({session}).",
                                category=StaffNotification.CATEGORY_RESULTS,
                            )
                    messages.success(request, f"{updated} result entries approved.")
                else:
                    messages.info(request, "No submitted results found to approve.")
            elif action == "release":
                if not scoped_results.exists():
                    messages.error(request, "No results found for selected scope.")
                else:
                    school_class = None
                    if class_name:
                        school_class = SchoolClass.objects.filter(name__iexact=class_name).first()
                        if not school_class:
                            school_class, _ = SchoolClass.objects.get_or_create(name=class_name)
                    target_classes = [school_class] if school_class else _classes_from_results(scoped_results)
                    missing_snapshots = []
                    invalid_snapshots = []
                    for cls in target_classes:
                        snapshot = ResultSnapshot.objects.filter(
                            session=session, term=term, school_class=cls
                        ).first()
                        if not snapshot:
                            missing_snapshots.append(cls.name)
                            continue
                        is_valid, reason, _ = verify_snapshot(snapshot)
                        if not is_valid:
                            if reason:
                                invalid_snapshots.append(f"{cls.name} ({reason})")
                            else:
                                invalid_snapshots.append(cls.name)
                    if missing_snapshots or invalid_snapshots:
                        if missing_snapshots:
                            messages.error(
                                request,
                                "Missing approval snapshots for: "
                                + ", ".join(sorted(missing_snapshots))
                                + ".",
                            )
                        if invalid_snapshots:
                            messages.error(
                                request,
                                "Invalid approval snapshots for: "
                                + ", ".join(sorted(invalid_snapshots))
                                + ".",
                            )
                        return redirect("results:release_results")
                    try:
                        created, notification_count = release_results_workflow(
                            session, term, request.user, school_class=school_class
                        )
                    except ValueError as exc:
                        messages.error(request, str(exc))
                        return redirect("results:release_results")
                    if not created:
                        messages.info(request, "Results already released for this selection.")
                    else:
                        students_qs = _scoped_students(school_class=school_class)
                        for student in students_qs:
                            subject, body = format_result_release_email(student, term, session)
                            send_parent_email(subject, body, student)
                        target_classes = [school_class] if school_class else _classes_from_results(scoped_results)
                        releaser_name = request.user.get_full_name() or request.user.username
                        for cls in target_classes:
                            subject, body = format_teacher_result_released_email(
                                cls, term, session, releaser_name=releaser_name
                            )
                            send_teacher_emails_for_class(subject, body, cls)
                            teachers = User.objects.filter(is_teacher=True, teacher_class=cls)
                            for teacher in teachers:
                                create_staff_notification(
                                    teacher,
                                    f"Results released for {cls} - {term} ({session}).",
                                    category=StaffNotification.CATEGORY_RESULTS,
                                )
                        messages.success(
                            request,
                            f"Results released and {notification_count} notifications created.",
                        )
            else:
                school_class = None
                if class_name:
                    school_class = SchoolClass.objects.filter(name__iexact=class_name).first()
                    if not school_class:
                        school_class, _ = SchoolClass.objects.get_or_create(name=class_name)
                reason = (request.POST.get("reopen_reason") or "").strip()
                if not reason:
                    reason = "Reopened for corrections."
                try:
                    reopened_count, removed_releases = reopen_results_workflow(
                        session=session,
                        term=term,
                        user=request.user,
                        school_class=school_class,
                        reason=reason,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("results:release_results")
                messages.success(
                    request,
                    f"Workflow reopened. {reopened_count} result entries unlocked; "
                    f"{removed_releases} release record(s) removed.",
                )

    selected_class = normalize_class_name(request.GET.get("class_name"))
    summary = {}
    if session and term:
        scoped_results = _scoped_results(session, term, selected_class)
        summary = {
            "total": scoped_results.count(),
            "draft": scoped_results.filter(status=Result.STATUS_DRAFT).count(),
            "submitted": scoped_results.filter(status=Result.STATUS_SUBMITTED).count(),
            "approved": scoped_results.filter(status=Result.STATUS_APPROVED).count(),
        }

    snapshots = []
    snapshot_health = {"total": 0, "valid": 0, "invalid": 0, "missing": 0}
    if session and term:
        snapshots_qs = (
            ResultSnapshot.objects.filter(session=session, term=term)
            .select_related("school_class", "approved_by", "invalidated_by")
            .order_by("school_class__name")
        )
        snapshots = list(snapshots_qs)
        valid_count = 0
        invalid_count = 0
        for row in snapshots:
            is_valid, _, _ = verify_snapshot(row)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        expected_classes = _classes_from_results(_scoped_results(session, term, selected_class))
        snapshot_class_ids = {
            snap.school_class_id
            for snap in snapshots
            if snap.school_class_id is not None
        }
        missing_count = sum(1 for cls in expected_classes if cls.id not in snapshot_class_ids)
        snapshot_health = {
            "total": len(snapshots),
            "valid": valid_count,
            "invalid": invalid_count,
            "missing": missing_count,
        }

    context = {
        "sessions": sessions,
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
        "selected_class": selected_class,
        "class_names": class_names,
        "summary": summary,
        "snapshots": snapshots,
        "snapshot_health": snapshot_health,
    }
    return render(request, "results/release_results.html", context)


@proprietor_required
def snapshot_verification(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    snapshots = []
    if session and term:
        snapshot_qs = (
            ResultSnapshot.objects.filter(session=session, term=term)
            .select_related("school_class", "approved_by", "invalidated_by")
            .order_by("school_class__name")
        )
        for snap in snapshot_qs:
            is_valid, reason, recalculated_hash = verify_snapshot(snap)
            snapshots.append(
                {
                    "snapshot": snap,
                    "is_valid": is_valid,
                    "reason": reason,
                    "recalculated_hash": recalculated_hash,
                }
            )

    return render(
        request,
        "results/snapshot_verification.html",
        {
            "sessions": AcademicSession.objects.all().order_by("-id"),
            "terms": Term.objects.filter(session=session).order_by("order") if session else [],
            "selected_session": session,
            "selected_term": term,
            "snapshots": snapshots,
        },
    )

def ensure_teacher_class(request):
    if not getattr(request.user, "teacher_class", None):
        return render(request, "accounts/no_class_assigned.html")
    return None


def _scoped_results(session, term, class_name=""):
    queryset = Result.objects.filter(session=session, term=term)
    normalized = normalize_class_name(class_name)
    if normalized:
        queryset = queryset.filter(
            Q(student__school_class__name__iexact=normalized)
            | Q(student__school_class__isnull=True, student__class_name__iexact=normalized)
        )
    return queryset


RELEASE_ACTION_CAPABILITY_MAP = {
    "approve": CAP_APPROVE_RESULTS,
    "release": CAP_RELEASE_RESULTS,
    "reopen": CAP_APPROVE_RESULTS,
}


RELEASE_ACTION_ERROR = {
    CAP_APPROVE_RESULTS: "You are not authorized to approve results.",
    CAP_RELEASE_RESULTS: "You are not authorized to release results.",
}


def _can_view_released_result(student, session, term):
    student_class = normalize_class_name(student.class_name)
    return ResultRelease.objects.filter(
        session=session,
        term=term,
    ).filter(
        Q(class_name="") | Q(class_name__iexact=student_class)
    ).exists()


def _released_terms_for_student(student, session):
    if not session:
        return Term.objects.none()
    student_class = normalize_class_name(student.class_name)
    released_term_ids = (
        ResultRelease.objects.filter(session=session)
        .filter(Q(class_name="") | Q(class_name__iexact=student_class))
        .values_list("term_id", flat=True)
        .distinct()
    )
    return Term.objects.filter(session=session, id__in=released_term_ids).order_by("order")


@never_cache
@ensure_csrf_cookie
def parent_portal_login(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    terms = Term.objects.select_related("session").order_by("session__name", "order")
    form = ParentPortalLoginForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            username = (form.cleaned_data.get("username") or "").strip()
            password = (form.cleaned_data.get("password") or "").strip()
            admission_number = (form.cleaned_data.get("admission_number") or "").strip()
            parent_surname = (form.cleaned_data.get("parent_surname") or "").strip().lower()

            if username and password:
                # Allow parent login with either username or email.
                login_identity = username
                if "@" in username:
                    user_model = get_user_model()
                    candidate = user_model.objects.filter(email__iexact=username).first()
                    if candidate:
                        login_identity = candidate.username
                user = authenticate(request, username=login_identity, password=password)
                parent_account = (
                    ParentPortalAccount.objects.select_related("student", "user")
                    .filter(user=user, is_active=True)
                    .first()
                    if user
                    else None
                )
                if not parent_account:
                    messages.error(request, "Invalid parent account credentials.")
                else:
                    request.session["parent_student_id"] = parent_account.student_id
                    request.session["parent_login_mode"] = "account"
                    ip_address = request.META.get("REMOTE_ADDR", "")
                    user_agent = request.META.get("HTTP_USER_AGENT", "")[:200]
                    subject, body = format_parent_login_email(
                        parent_account.student,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    notify_parent_event(
                        parent_account.student,
                        "Successful parent portal login detected.",
                        category=Notification.CATEGORY_ACCOUNT,
                        send_email=True,
                        email_subject=subject,
                        email_body=body,
                    )
                    messages.info(request, "Security alert logged for this login.")
                    return redirect("results:parent_dashboard")
            else:
                student = Student.objects.filter(admission_number=admission_number).first()
                if not student:
                    messages.error(request, "Invalid admission number.")
                elif (student.last_name or "").strip().lower() != parent_surname:
                    messages.error(request, "Surname does not match our record.")
                else:
                    request.session["parent_student_id"] = student.id
                    request.session["parent_login_mode"] = "legacy"
                    ip_address = request.META.get("REMOTE_ADDR", "")
                    user_agent = request.META.get("HTTP_USER_AGENT", "")[:200]
                    subject, body = format_parent_login_email(
                        student,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    notify_parent_event(
                        student,
                        "Successful parent portal login detected (legacy mode).",
                        category=Notification.CATEGORY_ACCOUNT,
                        send_email=True,
                        email_subject=subject,
                        email_body=body,
                    )
                    messages.info(request, "Security alert logged for this login.")
                    messages.warning(
                        request,
                        "Legacy surname login is deprecated. Please request a parent account username/password.",
                    )
                    return redirect("results:parent_dashboard")

    return render(
        request,
        "results/parent_login.html",
        {"sessions": sessions, "terms": terms, "form": form},
    )


def parent_portal_logout(request):
    request.session.pop("parent_student_id", None)
    return redirect("results:parent_login")


def parent_mark_notifications_read(request):
    if request.method != "POST":
        return redirect("results:parent_dashboard")

    student_id = request.session.get("parent_student_id")
    if not student_id:
        messages.error(request, "Login required.")
        return redirect("results:parent_login")

    Notification.objects.filter(student_id=student_id, is_read=False).update(is_read=True)
    messages.success(request, "Notifications marked as read.")
    return redirect("results:parent_dashboard")


def parent_mark_notification_read(request, notification_id):
    if request.method != "POST":
        return redirect("results:parent_dashboard")

    student_id = request.session.get("parent_student_id")
    if not student_id:
        messages.error(request, "Login required.")
        return redirect("results:parent_login")

    notification = get_object_or_404(Notification, id=notification_id, student_id=student_id)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    messages.success(request, "Notification marked as read.")
    return redirect("results:parent_dashboard")


def parent_notifications(request):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        return redirect("results:parent_login")
    student = get_object_or_404(Student, id=student_id)
    notifications = Notification.objects.filter(student=student).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()
    grouped = defaultdict(list)
    for note in notifications:
        grouped[note.category].append(note)
    ordered_grouped = {}
    category_order = [
        Notification.CATEGORY_RESULTS,
        Notification.CATEGORY_FINANCE,
        Notification.CATEGORY_ACCOUNT,
        Notification.CATEGORY_SYSTEM,
    ]
    for category in category_order:
        if grouped.get(category):
            ordered_grouped[category] = grouped[category]
    for category, notes in grouped.items():
        if category not in ordered_grouped:
            ordered_grouped[category] = notes
    category_labels = dict(Notification.CATEGORY_CHOICES)
    return render(
        request,
        "results/parent_notifications.html",
        {
            "student": student,
            "notifications": notifications,
            "unread_count": unread_count,
            "grouped_notifications": ordered_grouped,
            "category_labels": category_labels,
        },
    )


def parent_dashboard(request):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        return redirect("results:parent_login")

    student = get_object_or_404(Student, id=student_id)
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    released_terms = _released_terms_for_student(student, session)
    released_term_ids = set(released_terms.values_list("id", flat=True))

    if request.GET.get("term"):
        requested_term = Term.objects.filter(id=request.GET.get("term"), session=session).first()
        if requested_term and requested_term.id in released_term_ids:
            term = requested_term
        else:
            term = released_terms.first()
    elif term and term.id not in released_term_ids:
        term = released_terms.first()

    results = (
        Result.objects.filter(student=student, session=session, term=term)
        .select_related("subject")
        .order_by("subject__name")
    )
    domain_assessment = StudentDomainAssessment.objects.filter(
        student=student, session=session, term=term
    ).first()

    if not (session and term and _can_view_released_result(student, session, term)):
        messages.error(request, "Selected result is not released yet.")
        results = Result.objects.none()

    term_total = sum(result.total_score for result in results)
    average = round(term_total / results.count(), 2) if results.exists() else 0

    class_student_ids = list(
        Student.objects.filter(class_name=student.class_name).values_list("id", flat=True)
    )
    term_rank_display = ""
    session_rank_display = ""
    show_cumulative = bool(term and term.order == 3)
    term_totals = {1: 0, 2: 0, 3: 0}
    cumulative_total = 0
    cumulative_average = 0
    pass_fail = ""
    attendance_rate = 0.0
    behavior_average = 0.0
    psychomotor_average = 0.0
    promotion_status = "PENDING"
    promotion_reason = "Awaiting evaluation."
    session_snapshot = {}

    if session and term and class_student_ids:
        term_totals_map = build_term_totals_map_for_ids(session, term, class_student_ids)
        term_rows = [{"student_id": sid, "total": term_totals_map.get(sid, 0)} for sid in class_student_ids]
        rank_students(term_rows)
        term_rank_display = next(
            (row["rank_display"] for row in term_rows if row["student_id"] == student.id),
            "",
        )

        session_totals_map = build_session_totals_map_for_ids(session, class_student_ids)
        session_rows = [{"student_id": sid, "total": session_totals_map.get(sid, 0)} for sid in class_student_ids]
        rank_students(session_rows)
        session_rank_display = next(
            (row["rank_display"] for row in session_rows if row["student_id"] == student.id),
            "",
        )
        session_snapshot = compute_student_session_snapshot(session, class_student_ids)

    if show_cumulative and session_snapshot:
        student_snapshot = session_snapshot.get(student.id, {})
        term_totals = student_snapshot.get("term_totals", term_totals)
        cumulative_total = student_snapshot.get("cumulative_total", 0)
        cumulative_average = student_snapshot.get("cumulative_average", 0)
        attendance_rate = student_snapshot.get("attendance_rate", 0.0)
        behavior_average = student_snapshot.get("behavior_average", 0.0)
        psychomotor_average = student_snapshot.get("psychomotor_average", 0.0)
        promotion_status = student_snapshot.get("promotion_status", "PENDING")
        promotion_reason = student_snapshot.get("promotion_reason", "Awaiting evaluation.")
        pass_fail = student_snapshot.get("pass_fail", "")
        attendance_rate = student_snapshot.get("attendance_rate", 0.0)
        behavior_average = student_snapshot.get("behavior_average", 0.0)
        psychomotor_average = student_snapshot.get("psychomotor_average", 0.0)
        promotion_status = student_snapshot.get("promotion_status", "PENDING")
        promotion_reason = student_snapshot.get("promotion_reason", "Awaiting evaluation.")

    invoice_totals = {"billed": 0, "paid": 0, "balance": 0}
    recent_receipts = []
    try:
        from billing.models import Invoice, Payment

        invoices = Invoice.objects.filter(student=student).prefetch_related("items", "payments")
        invoice_totals = {
            "billed": sum(invoice.total_amount for invoice in invoices),
            "paid": sum(invoice.paid_amount for invoice in invoices),
            "balance": sum(invoice.balance for invoice in invoices),
        }
        recent_receipts = Payment.objects.filter(invoice__student=student).order_by("-paid_at")[:6]
    except Exception:
        pass

    notifications = Notification.objects.filter(student=student)[:6]
    unread_count = Notification.objects.filter(student=student, is_read=False).count()

    return render(
        request,
        "results/parent_dashboard.html",
        {
            "student": student,
            "results": results,
            "sessions": AcademicSession.objects.all().order_by("-id"),
            "terms": released_terms,
            "selected_session": session,
            "selected_term": term,
            "term_total": term_total,
            "average": average,
            "term_rank_display": term_rank_display,
            "session_rank_display": session_rank_display,
            "show_cumulative": show_cumulative,
            "term_totals": term_totals,
            "cumulative_total": cumulative_total,
            "cumulative_average": cumulative_average,
            "pass_fail": pass_fail,
            "attendance_rate": attendance_rate,
            "behavior_average": behavior_average,
            "psychomotor_average": psychomotor_average,
            "promotion_status": promotion_status,
            "promotion_reason": promotion_reason,
            "domain_assessment": domain_assessment,
            "invoice_totals": invoice_totals,
            "recent_receipts": recent_receipts,
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


def parent_wallet(request):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        return redirect("results:parent_login")

    student = get_object_or_404(Student, id=student_id)
    student_class = normalize_class_name(student.class_name)

    releases = (
        ResultRelease.objects.filter(Q(class_name="") | Q(class_name__iexact=student_class))
        .select_related("session", "term")
        .order_by("-session_id", "-term__order")
    )

    result_wallet = []
    for release in releases:
        has_result = Result.objects.filter(
            student=student, session=release.session, term=release.term
        ).exists()
        if not has_result:
            continue
        result_wallet.append(
            {
                "session": release.session,
                "term": release.term,
                "released_at": release.released_at,
            }
        )

    invoice_totals = {"billed": 0, "paid": 0, "balance": 0}
    receipts = []
    try:
        from billing.models import Invoice, Payment

        invoices = Invoice.objects.filter(student=student).prefetch_related("items", "payments")
        invoice_totals = {
            "billed": sum(invoice.total_amount for invoice in invoices),
            "paid": sum(invoice.paid_amount for invoice in invoices),
            "balance": sum(invoice.balance for invoice in invoices),
        }
        receipts = (
            Payment.objects.filter(invoice__student=student)
            .select_related("invoice", "invoice__session", "invoice__term")
            .order_by("-paid_at")
        )
    except Exception:
        receipts = []

    return render(
        request,
        "results/parent_wallet.html",
        {
            "student": student,
            "result_wallet": result_wallet,
            "receipts": receipts,
            "invoice_totals": invoice_totals,
        },
    )


def parent_portal(request):
    return redirect("results:parent_dashboard")


def check_result(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    terms = Term.objects.none()
    admission_number = (request.GET.get("admission_number") or "").strip()
    selected_session = AcademicSession.objects.filter(id=request.GET.get("session")).first() if request.GET.get("session") else None
    selected_term = None

    if admission_number and selected_session:
        student_for_filter = Student.objects.filter(admission_number=admission_number).first()
        if student_for_filter:
            terms = _released_terms_for_student(student_for_filter, selected_session)

    if request.method == "POST":
        reg_no = (request.POST.get("admission_number") or "").strip()
        session_id = request.POST.get("session")
        term_id = request.POST.get("term")

        student = Student.objects.filter(admission_number=reg_no).first()
        session = AcademicSession.objects.filter(id=session_id).first()
        available_terms = _released_terms_for_student(student, session) if (student and session) else Term.objects.none()
        term = available_terms.filter(id=term_id).first()
        selected_session = session
        selected_term = term
        admission_number = reg_no
        terms = available_terms

        if not student or not session or not term:
            return render(
                request,
                "results/check.html",
                {
                    "error": "Result not found for the selected session/term.",
                    "sessions": sessions,
                    "terms": terms,
                    "selected_session": selected_session,
                    "selected_term": selected_term,
                    "admission_number": admission_number,
                },
            )

        release_exists = _can_view_released_result(student, session, term)
        if not release_exists:
            return render(
                request,
                "results/check.html",
                {
                    "error": "Result not released yet for the selected session/term.",
                    "sessions": sessions,
                    "terms": terms,
                    "selected_session": selected_session,
                    "selected_term": selected_term,
                    "admission_number": admission_number,
                },
            )

        results = (
            Result.objects.filter(student=student, session=session, term=term)
            .select_related("subject")
            .order_by("subject__name")
        )

        term_total = sum(result.total_score for result in results)
        average = round(term_total / results.count(), 2) if results.exists() else 0

        session_terms = list(Term.objects.filter(session=session).order_by("order"))
        student_snapshot = compute_student_session_snapshot(session, [student.id]).get(student.id, {})
        term_totals_map = student_snapshot.get("term_totals", {})
        term_avg_map = student_snapshot.get("term_averages", {})
        session_term_totals = [
            {"term": session_term, "total": term_totals_map.get(session_term.order, 0)}
            for session_term in session_terms
        ]
        session_term_averages = [
            {"term": session_term, "average": term_avg_map.get(session_term.order, 0)}
            for session_term in session_terms
        ]

        promotion_average = (
            round(sum(item["total"] for item in session_term_totals) / 3, 2)
            if session_term_totals
            else 0
        )
        cumulative_total = student_snapshot.get("cumulative_total", 0)
        cumulative_average = student_snapshot.get("cumulative_average", 0)

        class_student_ids = list(
            Student.objects.filter(class_name=student.class_name).values_list("id", flat=True)
        )

        # Term rank
        term_totals = build_term_totals_map_for_ids(session, term, class_student_ids)
        term_rows = [
            {"student_id": student_id, "total": term_totals.get(student_id, 0)}
            for student_id in class_student_ids
        ]
        rank_students(term_rows)
        term_rank = next(
            (row["rank"] for row in term_rows if row["student_id"] == student.id), None
        )
        term_rank_display = ordinal(term_rank)

        # Session rank (sum of 3 terms)
        session_totals = build_session_totals_map_for_ids(session, class_student_ids)
        session_rows = [
            {"student_id": student_id, "total": session_totals.get(student_id, 0)}
            for student_id in class_student_ids
        ]
        rank_students(session_rows)
        session_rank = next(
            (row["rank"] for row in session_rows if row["student_id"] == student.id),
            None,
        )
        session_rank_display = ordinal(session_rank)
        release_info = ResultRelease.objects.filter(
            session=session,
            term=term,
            class_name__in=["", student.class_name or ""],
        ).order_by("-released_at").first()
        domain_assessment = StudentDomainAssessment.objects.filter(
            student=student, session=session, term=term
        ).first()

        return render(
            request,
            "results/result_detail.html",
            {
                "student": student,
                "results": results,
                "session": session,
                "term": term,
                "term_total": term_total,
                "average": average,
                "session_term_totals": session_term_totals,
                "session_term_averages": session_term_averages,
                "promotion_average": promotion_average,
                "cumulative_total": cumulative_total,
                "cumulative_average": cumulative_average,
                "attendance_rate": attendance_rate,
                "behavior_average": behavior_average,
                "psychomotor_average": psychomotor_average,
                "promotion_status": promotion_status,
                "promotion_reason": promotion_reason,
                "cumulative_rank_display": session_rank_display,
                "term_rank": term_rank,
                "session_rank": session_rank,
                "term_rank_display": term_rank_display,
                "session_rank_display": session_rank_display,
                "release_info": release_info,
                "domain_assessment": domain_assessment,
            },
        )

    return render(
        request,
        "results/check.html",
        {
            "sessions": sessions,
            "terms": terms,
            "selected_session": selected_session,
            "selected_term": selected_term,
            "admission_number": admission_number,
        },
    )


def download_result_pdf(request, student_id, session_id, term_id):
    student = get_object_or_404(Student, id=student_id)
    session = get_object_or_404(AcademicSession, id=session_id)
    term = get_object_or_404(Term, id=term_id, session=session)
    if not _can_view_released_result(student, session, term):
        return HttpResponseForbidden("Result not released yet for this session/term.")
    results = Result.objects.filter(student=student, session=session, term=term)
    summary = None
    position_display = ""
    domain_assessment = StudentDomainAssessment.objects.filter(
        student=student, session=session, term=term
    ).first()

    class_student_ids = list(
        Student.objects.filter(class_name=student.class_name).values_list("id", flat=True)
    )
    if term.order == 3:
        student_snapshot = compute_student_session_snapshot(session, [student.id]).get(student.id, {})
        term_totals = student_snapshot.get("term_totals", {1: 0, 2: 0, 3: 0})
        cumulative_total = student_snapshot.get("cumulative_total", 0)
        cumulative_average = student_snapshot.get("cumulative_average", 0)

        session_totals = build_session_totals_map_for_ids(session, class_student_ids)
        session_rows = [
            {"student_id": student_id, "total": session_totals.get(student_id, 0)}
            for student_id in class_student_ids
        ]
        rank_students(session_rows)
        position = next(
            (row["rank_display"] for row in session_rows if row["student_id"] == student.id),
            "",
        )

        pass_fail = student_snapshot.get("pass_fail", compute_pass_fail(cumulative_average))

        summary = {
            "term1_total": term_totals.get(1, ""),
            "term2_total": term_totals.get(2, ""),
            "term3_total": term_totals.get(3, ""),
            "cumulative_total": cumulative_total,
            "cumulative_average": cumulative_average,
            "pass_fail": pass_fail,
            "attendance_rate": student_snapshot.get("attendance_rate", 0.0),
            "behavior_average": student_snapshot.get("behavior_average", 0.0),
            "psychomotor_average": student_snapshot.get("psychomotor_average", 0.0),
            "promotion_status": student_snapshot.get("promotion_status", "PENDING"),
            "promotion_reason": student_snapshot.get(
                "promotion_reason", "Awaiting evaluation."
            ),
            "position": position,
        }
        position_display = position
    else:
        term_totals = build_term_totals_map_for_ids(session, term, class_student_ids)
        term_rows = [
            {"student_id": student_id, "total": term_totals.get(student_id, 0)}
            for student_id in class_student_ids
        ]
        rank_students(term_rows)
        position_display = next(
            (row["rank_display"] for row in term_rows if row["student_id"] == student.id),
            "",
        )

    return generate_result_pdf(
        student,
        results,
        session,
        term,
        summary,
        position=position_display,
        domain_assessment=domain_assessment,
    )


@login_required
def download_all_results_pdf(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    if has_capability(request.user, CAP_VIEW_TEACHER_DASHBOARD) and getattr(
        request.user, "is_teacher", False
    ):
        students_qs = get_teacher_students(request.user)
    elif has_capability(request.user, CAP_VIEW_PROPRIETOR_DASHBOARD):
        students_qs = Student.objects.all()
    else:
        return HttpResponseForbidden("You are not authorized to download this report.")

    subjects = Subject.objects.all().order_by("name")
    students = list(students_qs.order_by("last_name", "first_name"))
    student_ids = [student.id for student in students]
    results = (
        Result.objects.filter(session=session, term=term, student_id__in=student_ids)
        .select_related("student", "subject")
    )

    result_map = defaultdict(dict)
    for result in results:
        result_map[result.student_id][result.subject_id] = result

    students_data = []
    for student in students:
        subject_data = {}
        total_score = 0
        count = 0
        student_results = result_map.get(student.id, {})
        for subject in subjects:
            result = student_results.get(subject.id)
            if result:
                subject_data[subject.name] = {
                    "score": result.total_score,
                    "grade": result.grade(),
                }
                total_score += result.total_score
                count += 1
            else:
                subject_data[subject.name] = {"score": "", "grade": ""}
        average = round(total_score / count, 2) if count else 0
        students_data.append(
            {
                "student": student,
                "subjects": subject_data,
                "total": total_score,
                "average": average,
            }
        )

    show_cumulative = bool(term and term.order == 3)
    if show_cumulative:
        snapshot_map = compute_student_session_snapshot(session, student_ids)
        for data in students_data:
            student_id = data["student"].id
            snap = snapshot_map.get(student_id, {})
            data["cumulative_total"] = snap.get("cumulative_total", 0)
            data["cumulative_average"] = snap.get("cumulative_average", 0)
            data["term_totals"] = snap.get("term_totals", {})
            data["pass_fail"] = snap.get("pass_fail", compute_pass_fail(data["cumulative_average"]))
            data["promotion_status"] = snap.get("promotion_status", "PENDING")

    rank_students(students_data, total_key="cumulative_total" if show_cumulative else "total")

    density = (request.GET.get("density") or "").strip().lower()
    if density not in {"standard", "dense"}:
        density = None

    title = f"Results Sheet - {session} - {term}"
    return generate_all_results_pdf(
        title,
        subjects,
        students_data,
        show_cumulative=show_cumulative,
        density_override=density,
    )


@teacher_with_class_required
@capability_required(CAP_ENTER_RESULTS)
def add_result(request):
    if request.method == "POST":
        form = ResultForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Result saved successfully.")
            return redirect("accounts:teacher_dashboard")
        messages.error(request, "Please correct the highlighted errors.")
    else:
        form = ResultForm(user=request.user)

    if request.user.teacher_class:
        form.fields["student"].queryset = get_teacher_students(request.user)

    return render(request, "results/add_result.html", {"form": form})


@teacher_with_class_required
@capability_required(CAP_SUBMIT_RESULTS)
def submit_results_for_review(request):
    if request.method != "POST":
        return redirect("results:list")

    session = AcademicSession.objects.filter(id=request.POST.get("session")).first()
    term = Term.objects.filter(id=request.POST.get("term"), session=session).first()
    if not session or not term:
        messages.error(request, "Session and term are required.")
        return redirect("results:list")

    class_name = request.user.teacher_class.name
    scoped_results = _scoped_results(session, term, class_name=class_name)
    if not scoped_results.exists():
        messages.error(request, "No results found for your class in this term.")
        return redirect(f"/results/?session={session.id}&term={term.id}")

    try:
        updated = submit_results_for_class(session, term, request.user.teacher_class, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"/results/?session={session.id}&term={term.id}")
    if updated:
        messages.success(request, f"{updated} result entries submitted for approval.")
    else:
        messages.info(request, "No draft results found. Entries may already be submitted/approved.")

    return redirect(f"/results/?session={session.id}&term={term.id}")


@teacher_with_class_required
def result_list(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    student_scope = get_teacher_students(request.user)
    results = (
        Result.objects.select_related("student", "subject", "session", "term")
        .filter(session=session, term=term, student__in=student_scope)
        .order_by("student__last_name", "student__first_name", "subject__name")
    )

    students_results = defaultdict(list)
    for result in results:
        students_results[result.student].append(result)

    status_counts = {
        row["status"]: row["count"]
        for row in results.values("status").annotate(count=Count("id"))
    }

    context = {
        "students_results": dict(students_results),
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
        "status_counts": status_counts,
    }

    return render(request, "results/result_list.html", context)


@teacher_with_class_required
def student_results_sheet(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if request.user.teacher_class and student.class_name != request.user.teacher_class.name:
        return redirect("results:list")

    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    domain_assessment = StudentDomainAssessment.objects.filter(
        student=student, session=session, term=term
    ).first()
    domain_form = StudentDomainAssessmentForm(request.POST or None, instance=domain_assessment)
    if request.method == "POST":
        if not (session and term):
            messages.error(request, "Session and term are required to save domain scores.")
        else:
            release_exists = _can_view_released_result(student, session, term)
            workflow_locked = False
            student_class = resolve_student_class(student)
            if student_class:
                workflow = ResultWorkflow.objects.filter(
                    session=session, term=term, school_class=student_class
                ).first()
                if workflow and workflow.status in {
                    ResultWorkflow.STATUS_APPROVED,
                    ResultWorkflow.STATUS_RELEASED,
                }:
                    workflow_locked = True
            if release_exists or workflow_locked:
                messages.error(
                    request,
                    "Assessment is locked after approval/release. Reopen workflow to edit.",
                )
                return redirect(f"/results/student/{student.id}/?session={session.id}&term={term.id}")
            if domain_form.is_valid():
                assessment = domain_form.save(commit=False)
                assessment.student = student
                assessment.session = session
                assessment.term = term
                assessment.class_teacher = request.user
                assessment.save()
                messages.success(request, "Affective and psychomotor assessment saved.")
                return redirect(f"/results/student/{student.id}/?session={session.id}&term={term.id}")
            messages.error(request, "Please correct assessment errors.")

    subjects = Subject.objects.all().order_by("name")
    results = (
        Result.objects.filter(student=student, session=session, term=term)
        .select_related("subject")
        .order_by("subject__name")
    )

    result_map = {result.subject_id: result for result in results}
    term_total = sum(result.total_score for result in results)
    average = round(term_total / results.count(), 2) if results.exists() else 0

    class_student_ids = list(
        Student.objects.filter(class_name=student.class_name).values_list("id", flat=True)
    )

    # Term rank
    term_totals = build_term_totals_map_for_ids(session, term, class_student_ids)
    term_rows = [
        {"student_id": student_id, "total": term_totals.get(student_id, 0)}
        for student_id in class_student_ids
    ]
    rank_students(term_rows)
    term_rank = next(
        (row["rank"] for row in term_rows if row["student_id"] == student.id), None
    )
    term_rank_display = ordinal(term_rank)

    # Session rank
    session_terms = Term.objects.filter(session=session).order_by("order")
    session_totals = build_session_totals_map_for_ids(session, class_student_ids)
    session_rows = [
        {"student_id": student_id, "total": session_totals.get(student_id, 0)}
        for student_id in class_student_ids
    ]
    rank_students(session_rows)
    session_rank = next(
        (row["rank"] for row in session_rows if row["student_id"] == student.id),
        None,
    )
    session_rank_display = ordinal(session_rank)

    show_cumulative = bool(term and term.order == 3)
    term_totals = {}
    term_averages = {}
    subject_term_scores = {}
    subject_term_cum = {}
    cumulative_total = None
    cumulative_average = None
    if show_cumulative:
        student_snapshot = compute_student_session_snapshot(session, [student.id]).get(student.id, {})
        term_totals = student_snapshot.get("term_totals", {})
        term_averages = student_snapshot.get("term_averages", {})
        cumulative_total = student_snapshot.get("cumulative_total", 0)
        cumulative_average = student_snapshot.get("cumulative_average", 0)
        all_term_results = (
            Result.objects.filter(student=student, session=session, term__in=session_terms)
            .select_related("subject", "term")
        )
        for result in all_term_results:
            subject_term_scores.setdefault(result.subject_id, {})[
                result.term.order
            ] = result.total_score
            subject_term_cum[result.subject_id] = subject_term_cum.get(
                result.subject_id, 0
            ) + result.total_score

    return render(
        request,
        "results/single_student_result.html",
        {
            "student": student,
            "subjects": subjects,
            "results": results,
            "result_map": result_map,
            "term_total": term_total,
            "average": average,
            "sessions": AcademicSession.objects.all().order_by("-id"),
            "terms": Term.objects.filter(session=session).order_by("order") if session else [],
            "selected_session": session,
            "selected_term": term,
            "term_rank": term_rank,
            "session_rank": session_rank,
            "term_rank_display": term_rank_display,
            "session_rank_display": session_rank_display,
            "show_cumulative": show_cumulative,
            "term_totals": term_totals,
            "term_averages": term_averages,
            "subject_term_scores": subject_term_scores,
            "subject_term_cum": subject_term_cum,
            "cumulative_total": cumulative_total,
            "cumulative_average": cumulative_average,
            "domain_assessment": domain_assessment,
            "domain_form": domain_form,
        },
    )


@teacher_with_class_required
def results_sheet(request):
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)

    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    students = list(get_teacher_students(request.user).order_by("last_name", "first_name"))
    subjects = Subject.objects.all().order_by("name")

    student_ids = [student.id for student in students]
    results = (
        Result.objects.filter(session=session, term=term, student_id__in=student_ids)
        .select_related("student", "subject")
    )

    students_data = []

    result_map = {}
    for result in results:
        result_map.setdefault(result.student_id, {})[result.subject_id] = result

    term_scores = {}
    term_totals_map = defaultdict(dict)
    session_terms = Term.objects.filter(session=session).order_by("order")
    snapshot_map = compute_student_session_snapshot(session, student_ids) if session and student_ids else {}
    if term and term.order == 3 and student_ids:
        all_term_results = (
            Result.objects.filter(
                student_id__in=student_ids, session=session, term__in=session_terms
            )
            .select_related("subject", "term")
        )
        for res in all_term_results:
            term_scores.setdefault(res.student_id, {}).setdefault(res.term.order, {})[
                res.subject_id
            ] = res
            term_totals_map[res.student_id][res.term.order] = (
                term_totals_map[res.student_id].get(res.term.order, 0) + res.total_score
            )

    for student in students:
        subject_data = {}
        total_score = 0
        count = 0
        student_results = result_map.get(student.id, {})
        term_total_map = term_totals_map.get(student.id, {})

        for subject in subjects:
            result = student_results.get(subject.id)

            if result:
                subject_data[subject.name] = {
                    "score": result.total_score,
                    "grade": result.grade(),
                }
                total_score += result.total_score
                count += 1
            else:
                subject_data[subject.name] = {"score": "", "grade": ""}

            if term and term.order == 3:
                student_term_scores = term_scores.get(student.id, {})
                term_subject_scores = {
                    1: student_term_scores.get(1, {}).get(subject.id),
                    2: student_term_scores.get(2, {}).get(subject.id),
                    3: student_term_scores.get(3, {}).get(subject.id),
                }
                subject_data[subject.name].update(
                    {
                        "t1": term_subject_scores[1].total_score
                        if term_subject_scores[1]
                        else "",
                        "t2": term_subject_scores[2].total_score
                        if term_subject_scores[2]
                        else "",
                        "t3": term_subject_scores[3].total_score
                        if term_subject_scores[3]
                        else "",
                        "cum": (
                            (term_subject_scores[1].total_score if term_subject_scores[1] else 0)
                            + (term_subject_scores[2].total_score if term_subject_scores[2] else 0)
                            + (term_subject_scores[3].total_score if term_subject_scores[3] else 0)
                        ),
                    }
                )

        average = round(total_score / count, 2) if count else 0

        cumulative_total = None
        cumulative_average = None
        if term and term.order == 3:
            snap = snapshot_map.get(student.id, {})
            cumulative_total = snap.get("cumulative_total", 0)
            cumulative_average = snap.get("cumulative_average", 0)
            if snap.get("term_totals"):
                term_total_map = snap.get("term_totals", term_total_map)

        students_data.append(
            {
                "student": student,
                "subjects": subject_data,
                "total": total_score,
                "average": average,
                "cumulative_total": cumulative_total,
                "cumulative_average": cumulative_average,
                "term_totals": term_total_map,
            }
        )

    rank_students(students_data)

    # Session totals and ranks (sum of 3 terms)
    session_rows = []
    session_totals = {sid: payload.get("cumulative_total", 0) for sid, payload in snapshot_map.items()}
    for student in students:
        session_total = session_totals.get(student.id, 0)
        session_rows.append(
            {
                "student": student,
                "total": session_total,
                "average": round(session_total / 3, 2) if session_terms else 0,
            }
        )
    rank_students(session_rows)

    if term and term.order == 3:
        rank_students(students_data, total_key="cumulative_total")

    context = {
        "subjects": subjects,
        "students_data": students_data,
        "session_rows": session_rows,
        "show_cumulative": bool(term and term.order == 3),
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
    }

    return render(request, "results/results_sheet.html", context)
