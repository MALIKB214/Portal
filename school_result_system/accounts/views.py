from collections import defaultdict

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
import base64
import io
from pathlib import Path
from django.conf import settings
from django.core.management import call_command

from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.urls import reverse

from students.models import Student
from results.models import ParentPortalAccount, Result, ResultSnapshot, StudentDomainAssessment
from results.snapshot_service import verify_snapshot
from results.services import (
    compute_pass_fail,
    compute_student_session_snapshot,
    pass_mark,
    total_score_expression,
)
from academics.models import Subject, AcademicSession, Term
from .forms import ContactMessageForm, SchoolBrandingForm
from .models import SchoolBranding, StaffNotification, SystemEventLog
from .permissions import teacher_required, proprietor_required
from .permissions import can_access_staff_portal, default_dashboard_url
from .capabilities import (
    ALL_CAPABILITIES,
    MANAGED_ROLES,
    ROLE_CAPABILITIES,
    clear_capability_cache,
    get_role_capability_overrides,
)
from .notifications import (
    format_staff_login_email,
    notify_staff_event,
)
from .models import RoleCapabilityPolicy


def landing_page(request):
    brand = SchoolBranding.get_solo()
    contact_form = ContactMessageForm(request.POST or None)

    if request.method == "POST":
        if contact_form.is_valid():
            contact_form.save()
            messages.success(request, "Message sent. Our team will contact you shortly.")
            return redirect(f"{reverse('accounts:landing')}#contact")
        messages.error(request, "Please correct the contact form errors.")

    highlights = [
        "Balanced academic foundation across sciences, arts, and commercial subjects",
        "Strong moral discipline with leadership and character building",
        "WAEC/NECO readiness with continuous assessment tracking",
        "Qualified teachers with clear progress reporting",
        "Safe learning environment with mentorship and guidance",
        "Parent visibility through secure portal access",
    ]
    programs = [
        {
            "title": "Junior Secondary (JSS1–JSS3)",
            "desc": "Core foundation in English, Mathematics, Basic Science, Social Studies, ICT, and Vocational Studies.",
        },
        {
            "title": "Senior Secondary (SS1–SS3)",
            "desc": "Specialized tracks in Science, Arts, and Commercial studies with exam-focused preparation.",
        },
        {
            "title": "Co‑Curricular Development",
            "desc": "Clubs, debates, sports, leadership training, and practical skill acquisition.",
        },
    ]
    core_values = [
        "Discipline",
        "Respect",
        "Academic Excellence",
        "Integrity",
        "Leadership",
        "Service",
    ]
    gallery = [
        {
            "title": "Science & Innovation",
            "desc": "Laboratory practicals, STEM clubs, and project‑based learning.",
        },
        {
            "title": "Arts & Expression",
            "desc": "Creative arts, music, cultural days, and public speaking.",
        },
        {
            "title": "Sports & Teamwork",
            "desc": "Inter‑house sports, athletics, and wellness activities.",
        },
        {
            "title": "Leadership & Service",
            "desc": "Prefect mentoring, community service, and leadership training.",
        },
    ]
    history = {
        "year_founded": "2010",
        "founder": "Proprietor/Proprietress",
        "address": "Permanent Site, Ilorin, Kwara State",
        "message": (
            "Founded to provide disciplined, modern education, our school has grown into a trusted "
            "secondary institution known for consistent academic results and strong character formation."
        ),
    }
    anthem = {
        "title": f"{brand.school_name if brand else 'School'} Anthem",
        "lines": [
            "We rise with purpose, we stand with pride,",
            "In knowledge and character we abide,",
            "Our school, our light, our guiding flame,",
            "We uphold excellence, we honor the name.",
        ],
        "motto": brand.school_motto if brand else "Results and Records Portal",
    }

    return render(
        request,
        "accounts/landing.html",
        {
            "contact_form": contact_form,
            "highlights": highlights,
            "programs": programs,
            "core_values": core_values,
            "gallery": gallery,
            "history": history,
            "anthem": anthem,
            "brand": brand,
        },
    )


@proprietor_required
def branding_settings(request):
    brand = SchoolBranding.get_solo()
    form = SchoolBrandingForm(request.POST or None, request.FILES or None, instance=brand)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Branding settings updated successfully.")
            return redirect("accounts:branding_settings")
        messages.error(request, "Please correct the branding form errors.")

    return render(request, "accounts/branding_settings.html", {"form": form})


@proprietor_required
def role_permission_matrix(request):
    capability_labels = {
        cap: cap.replace(".", " ").replace("_", " ").title()
        for cap in ALL_CAPABILITIES
    }

    if request.method == "POST":
        for role in MANAGED_ROLES:
            selected = set(request.POST.getlist(f"role_{role}"))
            default_caps = ROLE_CAPABILITIES.get(role, set())
            for capability in ALL_CAPABILITIES:
                is_allowed = capability in selected
                default_allowed = capability in default_caps
                if is_allowed == default_allowed:
                    RoleCapabilityPolicy.objects.filter(
                        role=role, capability=capability
                    ).delete()
                    continue
                RoleCapabilityPolicy.objects.update_or_create(
                    role=role,
                    capability=capability,
                    defaults={"is_allowed": is_allowed},
                )

        clear_capability_cache()
        messages.success(request, "Role permission matrix updated.")
        return redirect("accounts:role_permission_matrix")

    overrides = get_role_capability_overrides()
    matrix = []
    for capability in ALL_CAPABILITIES:
        row = {
            "capability": capability,
            "label": capability_labels[capability],
            "roles": {},
        }
        for role in MANAGED_ROLES:
            default_allowed = capability in ROLE_CAPABILITIES.get(role, set())
            effective_allowed = overrides.get(role, {}).get(capability, default_allowed)
            row["roles"][role] = effective_allowed
        matrix.append(row)

    context = {
        "roles": MANAGED_ROLES,
        "matrix": matrix,
    }
    return render(request, "accounts/role_permission_matrix.html", context)


@never_cache
@ensure_csrf_cookie
def teacher_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if can_access_staff_portal(user):
                login(request, user)
                ip_address = request.META.get("REMOTE_ADDR", "")
                user_agent = request.META.get("HTTP_USER_AGENT", "")[:200]
                subject, body = format_staff_login_email(
                    user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                notify_staff_event(
                    user,
                    "Successful login detected on your staff account.",
                    category=StaffNotification.CATEGORY_ACCOUNT,
                    email_subject=subject,
                    email_body=body,
                    send_email=True,
                )
                messages.info(request, "Security alert logged for this login.")
                return redirect(default_dashboard_url(user))
            else:
                messages.error(request, "You are not authorized to access this portal.")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "accounts/login.html")


def teacher_logout(request):
    logout(request)
    return redirect("accounts:teacher_login")



@teacher_required
def teacher_dashboard(request):
    if not request.user.teacher_class:
        return render(request, "accounts/no_class_assigned.html")
    # Basic stats
    if request.user.teacher_class:
        students_qs = Student.objects.filter(
            Q(school_class=request.user.teacher_class)
            | Q(school_class__isnull=True, class_name=request.user.teacher_class.name)
        )
    else:
        students_qs = Student.objects.none()
    students_count = students_qs.count()
    results_count = Result.objects.filter(student__in=students_qs).count()

    # Latest 5 students (for mini preview)
    latest_students = list(
        students_qs.order_by("-id").only("id", "first_name", "last_name")[:5]
    )

    # All subjects for results sheet
    subjects = list(Subject.objects.all().only("id", "name").order_by("name"))

    # Prepare mini results sheet preview
    students_data_preview = []
    session = AcademicSession.objects.filter(is_active=True).first()
    term = Term.objects.filter(session=session, is_active=True).first() if session else None
    latest_ids = [student.id for student in latest_students]
    results = Result.objects.none()
    if latest_ids:
        if session and term:
            results = Result.objects.filter(
                student_id__in=latest_ids, session=session, term=term
            ).select_related("subject")
        else:
            results = Result.objects.filter(student_id__in=latest_ids).select_related(
                "subject"
            )
    results_map = defaultdict(list)
    for result in results:
        results_map[result.student_id].append(result)

    for student in latest_students:
        student_results = {subject.name: "" for subject in subjects}
        total_score = 0
        student_result_rows = results_map.get(student.id, [])
        for result in student_result_rows:
            student_results[result.subject.name] = result.grade()
            total_score += result.total_score
        average_score = total_score / len(student_result_rows) if student_result_rows else 0

        students_data_preview.append({
            "student": student,
            "results": student_results,
            "total": total_score,
            "average": round(average_score, 2)
        })

    context = {
        "students_count": students_count,
        "results_count": results_count,
        "subjects": subjects,
        "students_data_preview": students_data_preview,
        "session": session,
        "term": term,
    }

    return render(request, "accounts/teacher_dashboard.html", context)


@login_required
def staff_notifications(request):
    notifications = StaffNotification.objects.filter(user=request.user).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()
    grouped = defaultdict(list)
    for note in notifications:
        grouped[note.category].append(note)
    ordered_grouped = {}
    category_order = [
        StaffNotification.CATEGORY_RESULTS,
        StaffNotification.CATEGORY_FINANCE,
        StaffNotification.CATEGORY_ACCOUNT,
        StaffNotification.CATEGORY_SYSTEM,
    ]
    for category in category_order:
        if grouped.get(category):
            ordered_grouped[category] = grouped[category]
    for category, notes in grouped.items():
        if category not in ordered_grouped:
            ordered_grouped[category] = notes

    return render(
        request,
        "accounts/staff_notifications.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
            "grouped_notifications": ordered_grouped,
            "category_labels": dict(StaffNotification.CATEGORY_CHOICES),
        },
    )


@login_required
def staff_mark_notifications_read(request):
    if request.method != "POST":
        return redirect("accounts:staff_notifications")
    StaffNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, "Notifications marked as read.")
    return redirect("accounts:staff_notifications")


@login_required
def staff_mark_notification_read(request, notification_id):
    if request.method != "POST":
        return redirect("accounts:staff_notifications")
    notification = StaffNotification.objects.filter(user=request.user, id=notification_id).first()
    if notification and not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    messages.success(request, "Notification marked as read.")
    return redirect("accounts:staff_notifications")


@proprietor_required
def parent_email_audit(request):
    accounts = ParentPortalAccount.objects.select_related("user", "student").order_by(
        "student__class_name", "student__first_name", "student__last_name"
    )
    rows = []
    missing_count = 0
    for acct in accounts:
        user_email = (acct.user.email or "").strip()
        student_parent_email = (acct.student.parent_email or "").strip()
        student_email = (acct.student.email or "").strip()
        effective_email = user_email or student_parent_email or student_email
        has_email = bool(effective_email)
        if not has_email:
            missing_count += 1
        rows.append(
            {
                "account": acct,
                "user_email": user_email,
                "student_parent_email": student_parent_email,
                "student_email": student_email,
                "effective_email": effective_email,
                "has_email": has_email,
            }
        )

    context = {
        "rows": rows,
        "total_accounts": len(rows),
        "missing_count": missing_count,
    }
    return render(request, "accounts/parent_email_audit.html", context)


def _build_promotion_analytics(session, class_filter=""):
    if not session:
        return []
    students_qs = Student.objects.all()
    if class_filter:
        students_qs = students_qs.filter(class_name=class_filter)
    students = list(students_qs.order_by("class_name", "last_name", "first_name"))
    student_ids = [student.id for student in students]
    snapshot_map = compute_student_session_snapshot(session, student_ids)

    class_buckets = defaultdict(
        lambda: {"PROMOTED": 0, "NOT PROMOTED": 0, "PENDING": 0, "students": 0}
    )
    for student in students:
        class_name = student.class_name or "Unassigned"
        status = snapshot_map.get(student.id, {}).get("promotion_status", "PENDING")
        class_buckets[class_name]["students"] += 1
        class_buckets[class_name][status] += 1

    rows = []
    for class_name, bucket in sorted(class_buckets.items()):
        students_count = bucket["students"] or 1
        rows.append(
            {
                "class_name": class_name,
                "students": bucket["students"],
                "promoted": bucket["PROMOTED"],
                "not_promoted": bucket["NOT PROMOTED"],
                "pending": bucket["PENDING"],
                "promotion_rate": round((bucket["PROMOTED"] / students_count) * 100, 1),
            }
        )
    return rows


def _build_attendance_behavior_trends(session, class_filter="", student_id=None):
    terms = list(Term.objects.filter(session=session).order_by("order")) if session else []
    term_labels = [term.name for term in terms]
    term_order_map = {term.order: idx for idx, term in enumerate(terms)}

    class_attendance = [0.0 for _ in terms]
    class_behavior = [0.0 for _ in terms]
    class_counts = [0 for _ in terms]
    class_opened = [0 for _ in terms]
    class_present = [0 for _ in terms]

    student_attendance = [0.0 for _ in terms]
    student_behavior = [0.0 for _ in terms]
    student_counts = [0 for _ in terms]
    student_opened = [0 for _ in terms]
    student_present = [0 for _ in terms]

    if not session:
        return {
            "labels": term_labels,
            "class_attendance": class_attendance,
            "class_behavior": class_behavior,
            "student_attendance": student_attendance,
            "student_behavior": student_behavior,
        }

    domain_qs = StudentDomainAssessment.objects.filter(session=session).select_related("student", "term")
    if class_filter:
        domain_qs = domain_qs.filter(student__class_name=class_filter)
    for row in domain_qs:
        idx = term_order_map.get(getattr(row.term, "order", None))
        if idx is None:
            continue
        opened = row.times_school_opened or 0
        present = row.times_present or 0
        behavior_avg = (
            row.discipline
            + row.respect
            + row.punctuality
            + row.teamwork
            + row.leadership
            + row.moral_conduct
        ) / 6
        class_counts[idx] += 1
        class_opened[idx] += opened
        class_present[idx] += present
        class_behavior[idx] += behavior_avg
        if student_id and row.student_id == student_id:
            student_counts[idx] += 1
            student_opened[idx] += opened
            student_present[idx] += present
            student_behavior[idx] += behavior_avg

    for i in range(len(terms)):
        class_attendance[i] = (
            round((class_present[i] / class_opened[i]) * 100, 1) if class_opened[i] else 0.0
        )
        class_behavior[i] = (
            round(class_behavior[i] / class_counts[i], 2) if class_counts[i] else 0.0
        )
        student_attendance[i] = (
            round((student_present[i] / student_opened[i]) * 100, 1) if student_opened[i] else 0.0
        )
        student_behavior[i] = (
            round(student_behavior[i] / student_counts[i], 2) if student_counts[i] else 0.0
        )

    return {
        "labels": term_labels,
        "class_attendance": class_attendance,
        "class_behavior": class_behavior,
        "student_attendance": student_attendance,
        "student_behavior": student_behavior,
    }


@proprietor_required
def schedule_manager(request):
    try:
        from django_celery_beat.models import PeriodicTask
    except Exception:
        messages.error(request, "Celery beat is not installed.")
        return redirect("accounts:proprietor_dashboard")

    from academics.models import AcademicSession, Term
    import json

    if request.method == "POST":
        task_id = request.POST.get("task_id")
        action = request.POST.get("action")
        task = PeriodicTask.objects.filter(id=task_id).first()
        if not task:
            messages.error(request, "Schedule not found.")
        else:
            if action == "toggle":
                task.enabled = not task.enabled
                task.save(update_fields=["enabled"])
                messages.success(
                    request,
                    f"Schedule '{task.name}' is now {'enabled' if task.enabled else 'disabled'}.",
                )
                SystemEventLog.objects.create(
                    action="schedule.toggle",
                    detail=f"{task.name} => {'enabled' if task.enabled else 'disabled'}",
                    created_by=request.user,
                )
            elif action == "save_options":
                session_id = request.POST.get("session_id") or None
                term_id = request.POST.get("term_id") or None
                include_per_class = request.POST.get("include_per_class") == "on"
                kwargs = {}
                if session_id:
                    kwargs["session_id"] = int(session_id)
                if term_id:
                    kwargs["term_id"] = int(term_id)
                if include_per_class:
                    kwargs["include_per_class"] = True
                task.kwargs = json.dumps(kwargs)
                task.save(update_fields=["kwargs"])
                messages.success(request, f"Options saved for '{task.name}'.")
                SystemEventLog.objects.create(
                    action="schedule.options",
                    detail=f"{task.name} kwargs={task.kwargs}",
                    created_by=request.user,
                )
            elif action == "run_now":
                try:
                    from celery import current_app
                    payload = {}
                    if task.kwargs:
                        payload = json.loads(task.kwargs)
                    if (
                        request.POST.get("send_to_me") == "on"
                        and task.task
                        in [
                            "billing.tasks.send_weekly_finance_summary_task",
                            "results.tasks.send_release_reminders_task",
                        ]
                    ):
                        payload["notify_user_id"] = request.user.id
                    current_app.send_task(task.task, kwargs=payload)
                    messages.success(request, f"Triggered '{task.name}'.")
                    SystemEventLog.objects.create(
                        action="schedule.run_now",
                        detail=f"{task.name} kwargs={payload}",
                        created_by=request.user,
                    )
                except Exception as exc:
                    messages.error(request, f"Failed to run task: {exc}")
            elif action == "test_email":
                try:
                    payload = {}
                    if task.kwargs:
                        payload = json.loads(task.kwargs)
                    if task.task == "billing.tasks.send_weekly_finance_summary_task":
                        from billing.tasks import send_weekly_finance_summary_task

                        send_weekly_finance_summary_task(
                            notify_user_id=request.user.id, **payload
                        )
                    elif task.task == "results.tasks.send_release_reminders_task":
                        from results.tasks import send_release_reminders_task

                        send_release_reminders_task(
                            notify_user_id=request.user.id, **payload
                        )
                    else:
                        messages.error(request, "Test email is not supported for this task.")
                        return redirect("accounts:schedule_manager")
                    messages.success(request, "Test email sent (if recipients have email).")
                    SystemEventLog.objects.create(
                        action="schedule.test_email",
                        detail=f"{task.name} kwargs={task.kwargs or '{}'} to user {request.user.id}",
                        created_by=request.user,
                    )
                except Exception as exc:
                    messages.error(request, f"Failed to send test email: {exc}")
        return redirect("accounts:schedule_manager")

    tasks = list(
        PeriodicTask.objects.select_related(
            "interval", "crontab", "solar", "clocked"
        ).order_by("name")
    )
    sessions = AcademicSession.objects.all().order_by("-id")
    terms = Term.objects.all().order_by("session_id", "order")
    # Pre-parse kwargs for UI defaults
    for task in tasks:
        try:
            task.opts = json.loads(task.kwargs) if task.kwargs else {}
        except Exception:
            task.opts = {}
    return render(
        request,
        "accounts/schedule_manager.html",
        {"tasks": tasks, "sessions": sessions, "terms": terms},
    )


@proprietor_required
def system_health(request):
    try:
        from django_celery_beat.models import PeriodicTask
    except Exception:
        PeriodicTask = None

    tasks = []
    enabled_count = 0
    disabled_count = 0
    if PeriodicTask:
        tasks = list(
            PeriodicTask.objects.select_related(
                "interval", "crontab", "solar", "clocked"
            ).order_by("name")
        )
        enabled_count = len([t for t in tasks if t.enabled])
        disabled_count = len([t for t in tasks if not t.enabled])

    recent_logs = list(SystemEventLog.objects.select_related("created_by")[:12])

    db_path = Path(settings.DATABASES["default"]["NAME"])
    backup_dir = Path("backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_files = sorted(backup_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "backup_now":
            try:
                output = io.StringIO()
                call_command("backup_db", stdout=output)
                SystemEventLog.objects.create(
                    action="backup.created",
                    detail=output.getvalue()[:220],
                    created_by=request.user,
                )
                messages.success(request, "Backup created successfully.")
            except Exception as exc:
                messages.error(request, f"Backup failed: {exc}")
        elif action == "restore_backup":
            backup_name = (request.POST.get("backup_name") or "").strip()
            confirm = (request.POST.get("confirm_restore") or "").strip()
            if confirm != "RESTORE":
                messages.error(request, "Type RESTORE to confirm restore operation.")
            else:
                target = backup_dir / backup_name
                if not target.exists():
                    messages.error(request, "Selected backup file not found.")
                else:
                    try:
                        output = io.StringIO()
                        call_command("restore_db", str(target), yes=True, stdout=output)
                        SystemEventLog.objects.create(
                            action="backup.restored",
                            detail=f"restored={target.name}",
                            created_by=request.user,
                        )
                        messages.success(request, "Backup restored. Restart server recommended.")
                    except Exception as exc:
                        messages.error(request, f"Restore failed: {exc}")
        elif action == "ensure_backup_schedule":
            try:
                from django_celery_beat.models import IntervalSchedule, PeriodicTask

                interval, _ = IntervalSchedule.objects.get_or_create(
                    every=1,
                    period="days",
                )
                PeriodicTask.objects.get_or_create(
                    name="daily-db-backup",
                    defaults={
                        "task": "accounts.tasks.backup_database_task",
                        "interval": interval,
                        "enabled": True,
                        "description": "Automated daily sqlite backup",
                    },
                )
                messages.success(request, "Daily backup schedule is configured.")
            except Exception as exc:
                messages.error(request, f"Could not configure schedule: {exc}")
        return redirect("accounts:system_health")

    backup_schedule = None
    try:
        from django_celery_beat.models import PeriodicTask

        backup_schedule = PeriodicTask.objects.filter(name="daily-db-backup").first()
    except Exception:
        backup_schedule = None

    context = {
        "broker_url": getattr(settings, "CELERY_BROKER_URL", ""),
        "result_backend": getattr(settings, "CELERY_RESULT_BACKEND", ""),
        "beat_scheduler": getattr(settings, "CELERY_BEAT_SCHEDULER", ""),
        "worker_pool": getattr(settings, "CELERY_WORKER_POOL", ""),
        "tasks": tasks,
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "recent_logs": recent_logs,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "db_size_mb": round((db_path.stat().st_size / (1024 * 1024)), 2) if db_path.exists() else 0,
        "backup_files": backup_files[:20],
        "backup_schedule": backup_schedule,
    }
    return render(request, "accounts/system_health.html", context)

@proprietor_required
def proprietor_dashboard(request):
    if request.method == "POST" and request.POST.get("action") == "save_chart_prefs":
        request.user.analytics_chart_stacked = request.POST.get("stacked") == "true"
        request.user.analytics_chart_show_legend = request.POST.get("legend") == "true"
        request.user.save(
            update_fields=["analytics_chart_stacked", "analytics_chart_show_legend"]
        )
        redirect_url = request.POST.get("redirect_to") or "accounts:proprietor_dashboard"
        return redirect(redirect_url)

    session = AcademicSession.objects.filter(is_active=True).first()
    term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    snapshot_health = {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "missing": 0,
        "invalid_classes": [],
    }
    if session and term:
        workflow_classes = list(
            Result.objects.filter(session=session, term=term)
            .exclude(student__school_class__isnull=True)
            .values_list("student__school_class__name", flat=True)
            .distinct()
        )
        snapshot_rows = (
            ResultSnapshot.objects.filter(session=session, term=term)
            .select_related("school_class")
            .order_by("school_class__name")
        )
        invalid_classes = []
        valid_count = 0
        for row in snapshot_rows:
            is_valid, reason, _ = verify_snapshot(row)
            if is_valid:
                valid_count += 1
            else:
                invalid_classes.append(
                    {
                        "class_name": row.school_class.name,
                        "reason": reason,
                    }
                )
        total = snapshot_rows.count()
        snapshot_health = {
            "total": total,
            "valid": valid_count,
            "invalid": len(invalid_classes),
            "missing": max(len(workflow_classes) - total, 0),
            "invalid_classes": invalid_classes[:5],
        }

    students_count = Student.objects.count()
    results_count = Result.objects.count()

    total_collected = 0
    total_outstanding = 0
    invoices = []
    pending_payments = 0
    approved_today = 0
    invoice_status_counts = {}
    payment_status_counts = {}
    try:
        from billing.models import Invoice, Payment

        from billing.models import InvoiceItem

        invoices = (
            Invoice.objects.select_related("student", "session", "term")
            .order_by("-id")[:10]
        )
        total_billed = InvoiceItem.objects.aggregate(total=Sum("amount"))["total"] or 0
        total_collected = Payment.objects.filter(approval_status="approved").aggregate(
            total=Sum("amount")
        )["total"] or 0
        total_outstanding = max(total_billed - total_collected, 0)
        pending_payments = Payment.objects.filter(approval_status="pending").count()
        approved_today = Payment.objects.filter(
            approval_status="approved", approved_at__date=timezone.now().date()
        ).count()
        invoice_status_counts = {
            row["status"]: row["count"]
            for row in Invoice.objects.values("status").annotate(count=Count("id"))
        }
        payment_status_counts = {
            row["approval_status"]: row["count"]
            for row in Payment.objects.values("approval_status").annotate(count=Count("id"))
        }
        invoice_total_count = sum(invoice_status_counts.values())
        payment_total_count = sum(payment_status_counts.values())

        class_finance_breakdown = list(
            Payment.objects.filter(approval_status="approved", is_reversed=False)
            .values("invoice__student__class_name")
            .annotate(total=Sum("amount"))
            .order_by("invoice__student__class_name")
        )
    except Exception:
        invoices = []
        invoice_total_count = 0
        payment_total_count = 0
        class_finance_breakdown = []

    promotion_summary = []
    promotion_analytics = []
    if session:
        students_for_session = list(Student.objects.all().order_by("class_name", "last_name"))
        session_student_ids = [student.id for student in students_for_session]
        snapshot_map = compute_student_session_snapshot(session, session_student_ids)

        for student in students_for_session:
            snap = snapshot_map.get(student.id, {})
            promotion_summary.append(
                {
                    "student": student,
                    "average": snap.get("cumulative_average", 0),
                    "promotion_status": snap.get("promotion_status", "PENDING"),
                    "attendance_rate": snap.get("attendance_rate", 0.0),
                }
            )
        promotion_summary.sort(key=lambda row: row.get("average", 0), reverse=True)

        promotion_analytics = _build_promotion_analytics(session)

    trend_class = (request.GET.get("trend_class") or "").strip()
    trend_student = request.GET.get("trend_student")
    trend_student_id = int(trend_student) if trend_student and trend_student.isdigit() else None
    trend_students = list(
        Student.objects.filter(class_name=trend_class).order_by("last_name", "first_name")
    ) if trend_class else []
    trend_series = _build_attendance_behavior_trends(
        session=session,
        class_filter=trend_class,
        student_id=trend_student_id,
    )

    pass_fail_analytics = []
    class_top10 = {}
    analytics_term = term
    if session and term:
        class_counts = list(
            Student.objects.exclude(class_name__isnull=True)
            .exclude(class_name="")
            .values("class_name")
            .annotate(total=Count("id"))
            .order_by("class_name")
        )
        class_names = [row["class_name"] for row in class_counts]
        class_total_map = {row["class_name"]: row["total"] for row in class_counts}
        class_result_map = {name: {"pass": 0, "fail": 0} for name in class_names}

        if class_names:
            if term.order == 3:
                totals = list(
                    Result.objects.filter(
                        session=session, student__class_name__in=class_names
                    )
                    .values("student_id", "student__class_name")
                    .annotate(total=Sum(total_score_expression()))
                )
                for row in totals:
                    average = (row["total"] or 0) / 3
                    bucket = class_result_map.get(row["student__class_name"])
                    if not bucket:
                        continue
                    if compute_pass_fail(average) == "PASS":
                        bucket["pass"] += 1
                    else:
                        bucket["fail"] += 1
            else:
                totals = list(
                    Result.objects.filter(
                        session=session, term=term, student__class_name__in=class_names
                    )
                    .values("student_id", "student__class_name")
                    .annotate(total=Sum(total_score_expression()), count=Count("id"))
                )
                for row in totals:
                    average = (row["total"] or 0) / (row["count"] or 1)
                    bucket = class_result_map.get(row["student__class_name"])
                    if not bucket:
                        continue
                    if compute_pass_fail(average) == "PASS":
                        bucket["pass"] += 1
                    else:
                        bucket["fail"] += 1

        for class_name in class_names:
            passed = class_result_map.get(class_name, {}).get("pass", 0)
            failed = class_result_map.get(class_name, {}).get("fail", 0)
            evaluated = passed + failed
            pass_rate = round((passed / evaluated) * 100, 1) if evaluated else 0
            pass_fail_analytics.append(
                {
                    "class_name": class_name,
                    "total_students": class_total_map.get(class_name, 0),
                    "evaluated": evaluated,
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": pass_rate,
                }
            )

        # Top 10 per class
        if class_names:
            if term.order == 3:
                totals = list(
                    Result.objects.filter(session=session, student__class_name__in=class_names)
                    .values("student_id", "student__class_name")
                    .annotate(total=Sum(total_score_expression()))
                    .order_by("-total")
                )
            else:
                totals = list(
                    Result.objects.filter(
                        session=session, term=term, student__class_name__in=class_names
                    )
                    .values("student_id", "student__class_name")
                    .annotate(total=Sum(total_score_expression()))
                    .order_by("-total")
                )
            student_map = Student.objects.in_bulk([row["student_id"] for row in totals])
            for row in totals:
                class_name = row["student__class_name"]
                class_top10.setdefault(class_name, [])
                if len(class_top10[class_name]) >= 10:
                    continue
                student = student_map.get(row["student_id"])
                if not student:
                    continue
                class_top10[class_name].append(
                    {
                        "student": student,
                        "total": row["total"] or 0,
                    }
                )

    # Celery beat last run summary (optional)
    last_task_run = None
    try:
        from django_celery_beat.models import PeriodicTask

        last_task_run = (
            PeriodicTask.objects.exclude(last_run_at__isnull=True)
            .order_by("-last_run_at")
            .first()
        )
    except Exception:
        last_task_run = None

    context = {
        "students_count": students_count,
        "results_count": results_count,
        "session": session,
        "term": term,
        "total_collected": total_collected,
        "total_outstanding": total_outstanding,
        "pending_payments": pending_payments,
        "approved_today": approved_today,
        "recent_invoices": invoices,
        "promotion_summary": promotion_summary[:10],
        "promotion_analytics": promotion_analytics,
        "trend_class": trend_class,
        "trend_classes": (
            Student.objects.exclude(class_name__isnull=True)
            .exclude(class_name="")
            .values_list("class_name", flat=True)
            .distinct()
            .order_by("class_name")
        ),
        "trend_student_id": trend_student_id,
        "trend_students": trend_students,
        "trend_labels": trend_series["labels"],
        "trend_class_attendance": trend_series["class_attendance"],
        "trend_class_behavior": trend_series["class_behavior"],
        "trend_student_attendance": trend_series["student_attendance"],
        "trend_student_behavior": trend_series["student_behavior"],
        "invoice_status_counts": invoice_status_counts,
        "payment_status_counts": payment_status_counts,
        "invoice_total_count": invoice_total_count,
        "payment_total_count": payment_total_count,
        "class_finance_breakdown": class_finance_breakdown,
        "last_task_run": last_task_run,
        "pass_fail_analytics": pass_fail_analytics,
        "analytics_term": analytics_term,
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "class_top10": class_top10,
        "chart_pref_stacked": getattr(request.user, "analytics_chart_stacked", False),
        "chart_pref_legend": getattr(request.user, "analytics_chart_show_legend", True),
        "current_pass_mark": pass_mark(),
        "snapshot_health": snapshot_health,
    }

    return render(request, "accounts/proprietor_dashboard.html", context)


@proprietor_required
def analytics_export(request):
    data_source = request.POST if request.method == "POST" else request.GET
    session = AcademicSession.objects.filter(is_active=True).first()
    term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if data_source.get("session"):
        session = AcademicSession.objects.filter(id=data_source.get("session")).first()
        term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if data_source.get("term"):
        term = Term.objects.filter(id=data_source.get("term"), session=session).first()

    if not (session and term):
        return HttpResponse("Session and term required.", status=400)

    class_filter = (data_source.get("class_name") or "").strip()
    class_qs = Student.objects.exclude(class_name__isnull=True).exclude(class_name="")
    if class_filter:
        class_qs = class_qs.filter(class_name=class_filter)
    class_counts = list(
        class_qs.values("class_name")
        .annotate(total=Count("id"))
        .order_by("class_name")
    )
    class_names = [row["class_name"] for row in class_counts]
    class_total_map = {row["class_name"]: row["total"] for row in class_counts}
    class_result_map = {name: {"pass": 0, "fail": 0} for name in class_names}

    if class_names:
        if term.order == 3:
            totals = list(
                Result.objects.filter(session=session, student__class_name__in=class_names)
                .values("student_id", "student__class_name")
                .annotate(total=Sum(total_score_expression()))
            )
            for row in totals:
                average = (row["total"] or 0) / 3
                bucket = class_result_map.get(row["student__class_name"])
                if not bucket:
                    continue
                if compute_pass_fail(average) == "PASS":
                    bucket["pass"] += 1
                else:
                    bucket["fail"] += 1
        else:
            totals = list(
                Result.objects.filter(
                    session=session, term=term, student__class_name__in=class_names
                )
                .values("student_id", "student__class_name")
                .annotate(total=Sum(total_score_expression()), count=Count("id"))
            )
            for row in totals:
                average = (row["total"] or 0) / (row["count"] or 1)
                bucket = class_result_map.get(row["student__class_name"])
                if not bucket:
                    continue
                if compute_pass_fail(average) == "PASS":
                    bucket["pass"] += 1
                else:
                    bucket["fail"] += 1

    rows = []
    for class_name in class_names:
        passed = class_result_map.get(class_name, {}).get("pass", 0)
        failed = class_result_map.get(class_name, {}).get("fail", 0)
        evaluated = passed + failed
        pass_rate = round((passed / evaluated) * 100, 1) if evaluated else 0
        rows.append(
            {
                "class_name": class_name,
                "total_students": class_total_map.get(class_name, 0),
                "evaluated": evaluated,
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
            }
        )

    # Top 10 per class
    class_top10 = {}
    if class_names:
        if term.order == 3:
            totals = list(
                Result.objects.filter(session=session, student__class_name__in=class_names)
                .values("student_id", "student__class_name")
                .annotate(total=Sum(total_score_expression()))
                .order_by("-total")
            )
        else:
            totals = list(
                Result.objects.filter(
                    session=session, term=term, student__class_name__in=class_names
                )
                .values("student_id", "student__class_name")
                .annotate(total=Sum(total_score_expression()))
                .order_by("-total")
            )
        student_map = Student.objects.in_bulk([row["student_id"] for row in totals])
        for row in totals:
            class_name = row["student__class_name"]
            class_top10.setdefault(class_name, [])
            if len(class_top10[class_name]) >= 10:
                continue
            student = student_map.get(row["student_id"])
            if not student:
                continue
            class_top10[class_name].append(
                {
                    "student": student,
                    "total": row["total"] or 0,
                }
            )

    export_type = data_source.get("export", "csv")
    if export_type == "csv":
        filename = f"analytics_{session}_{term}.csv".replace(" ", "_")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write(
            "Class,Total Students,Evaluated,Passed,Failed,Pass Rate\n"
        )
        for row in rows:
            response.write(
                f"{row['class_name']},{row['total_students']},{row['evaluated']},"
                f"{row['passed']},{row['failed']},{row['pass_rate']}\n"
            )
        response.write("\nTop 10 Per Class\n")
        response.write("Class,Rank,Student,Total\n")
        for class_name, top_rows in class_top10.items():
            for idx, item in enumerate(top_rows, start=1):
                response.write(
                    f"{class_name},{idx},{item['student'].full_name},{item['total']}\n"
                )
        return response

    # PDF export (simple table)
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    filename = f"analytics_{session}_{term}.pdf".replace(" ", "_")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, f"Pass/Fail Analytics - {session} - {term}")

    chart_data = data_source.get("chart_image", "")
    if chart_data.startswith("data:image"):
        try:
            header, encoded = chart_data.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            image = ImageReader(io.BytesIO(image_bytes))
            y -= 180
            pdf.drawImage(image, 40, y, width=500, height=150, preserveAspectRatio=True, mask="auto")
            y -= 20
        except Exception:
            y -= 10

    y -= 30
    pdf.setFont("Helvetica-Bold", 10)
    headers = ["Class", "Total", "Evaluated", "Passed", "Failed", "Pass Rate"]
    col_widths = [120, 70, 70, 70, 70, 80]
    x = 40
    for width, header in zip(col_widths, headers):
        pdf.drawString(x + 2, y, header)
        x += width
    y -= 16
    pdf.setFont("Helvetica", 9)
    for row in rows:
        if y < 60:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 9)
        x = 40
        values = [
            row["class_name"],
            row["total_students"],
            row["evaluated"],
            row["passed"],
            row["failed"],
            f"{row['pass_rate']}%",
        ]
        for width, value in zip(col_widths, values):
            pdf.drawString(x + 2, y, str(value))
            x += width
        y -= 14

    pdf.showPage()
    y = height - 40
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Top 10 Per Class")
    y -= 20
    pdf.setFont("Helvetica", 9)
    for class_name, top_rows in class_top10.items():
        if y < 80:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 9)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(40, y, class_name)
        y -= 14
        pdf.setFont("Helvetica", 9)
        for idx, item in enumerate(top_rows, start=1):
            if y < 60:
                pdf.showPage()
                y = height - 40
                pdf.setFont("Helvetica", 9)
            pdf.drawString(60, y, f"{idx}. {item['student'].full_name}")
            pdf.drawRightString(500, y, str(item["total"]))
            y -= 12

    pdf.showPage()
    pdf.save()
    return response


@proprietor_required
def promotion_analytics_export(request):
    data_source = request.POST if request.method == "POST" else request.GET
    session = AcademicSession.objects.filter(is_active=True).first()
    if data_source.get("session"):
        session = AcademicSession.objects.filter(id=data_source.get("session")).first()
    if not session:
        return HttpResponse("Session required.", status=400)

    class_name = (data_source.get("class_name") or "").strip()
    rows = _build_promotion_analytics(session, class_filter=class_name)
    export_type = data_source.get("export", "csv")

    if export_type == "csv":
        filename = f"promotion_analytics_{session}.csv".replace(" ", "_")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("Class,Students,Promoted,Not Promoted,Pending,Promotion Rate\n")
        for row in rows:
            response.write(
                f"{row['class_name']},{row['students']},{row['promoted']},"
                f"{row['not_promoted']},{row['pending']},{row['promotion_rate']}\n"
            )
        return response

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    filename = f"promotion_analytics_{session}.pdf".replace(" ", "_")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)

    y = height - 40
    pdf.setFont("Helvetica-Bold", 13)
    title = f"Promotion Analytics - {session}"
    if class_name:
        title += f" ({class_name})"
    pdf.drawString(40, y, title)
    y -= 24

    pdf.setFont("Helvetica-Bold", 9)
    headers = ["Class", "Students", "Promoted", "Not Promoted", "Pending", "Promotion Rate"]
    col_x = [40, 250, 330, 410, 520, 610]
    for idx, header in enumerate(headers):
        pdf.drawString(col_x[idx], y, header)
    y -= 14
    pdf.setFont("Helvetica", 9)
    for row in rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 9)
        pdf.drawString(col_x[0], y, str(row["class_name"]))
        pdf.drawString(col_x[1], y, str(row["students"]))
        pdf.drawString(col_x[2], y, str(row["promoted"]))
        pdf.drawString(col_x[3], y, str(row["not_promoted"]))
        pdf.drawString(col_x[4], y, str(row["pending"]))
        pdf.drawString(col_x[5], y, f"{row['promotion_rate']}%")
        y -= 12

    pdf.showPage()
    pdf.save()
    return response


@proprietor_required
def setup_wizard(request):
    created_message = None
    error_message = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_session_terms":
            session_name = (request.POST.get("session_name") or "").strip()
            active_term_order = request.POST.get("active_term") or "1"
            if not session_name:
                error_message = "Session name is required."
            else:
                session, _created = AcademicSession.objects.get_or_create(name=session_name)
                if request.POST.get("set_active") == "on":
                    AcademicSession.objects.exclude(id=session.id).update(is_active=False)
                    session.is_active = True
                    session.save(update_fields=["is_active"])

                term_names = {
                    1: "First Term",
                    2: "Second Term",
                    3: "Third Term",
                }
                for order, name in term_names.items():
                    Term.objects.get_or_create(
                        session=session,
                        order=order,
                        defaults={"name": name},
                    )

                Term.objects.filter(session=session).update(is_active=False)
                try:
                    active_term_order = int(active_term_order)
                except ValueError:
                    active_term_order = 1
                Term.objects.filter(session=session, order=active_term_order).update(is_active=True)
                created_message = f"Session '{session.name}' and terms set up."

    session_count = AcademicSession.objects.count()
    active_session = AcademicSession.objects.filter(is_active=True).first()
    term_count = Term.objects.count()
    active_term = Term.objects.filter(is_active=True).first()

    from academics.models import SchoolClass
    class_count = SchoolClass.objects.count()
    subject_count = Subject.objects.count()

    student_count = Student.objects.count()

    fee_category_count = 0
    try:
        from billing.models import FeeCategory

        fee_category_count = FeeCategory.objects.count()
    except Exception:
        fee_category_count = 0

    steps = [
        {
            "name": "Academic Session",
            "done": session_count > 0 and active_session is not None,
            "detail": f"Total: {session_count}, Active: {'Yes' if active_session else 'No'}",
            "link": "/admin/academics/academicsession/",
        },
        {
            "name": "Terms (3 per session)",
            "done": term_count >= 3 and active_term is not None,
            "detail": f"Total: {term_count}, Active: {'Yes' if active_term else 'No'}",
            "link": "/admin/academics/term/",
        },
        {
            "name": "Classes",
            "done": class_count > 0,
            "detail": f"Total: {class_count}",
            "link": "/admin/academics/schoolclass/",
        },
        {
            "name": "Subjects",
            "done": subject_count > 0,
            "detail": f"Total: {subject_count}",
            "link": "/admin/academics/subject/",
        },
        {
            "name": "Students",
            "done": student_count > 0,
            "detail": f"Total: {student_count}",
            "link": "/admin/students/student/",
        },
        {
            "name": "Fee Categories",
            "done": fee_category_count >= 2,
            "detail": f"Total: {fee_category_count}",
            "link": "/admin/billing/feecategory/",
        },
    ]

    next_steps = [step for step in steps if not step["done"]]

    context = {
        "steps": steps,
        "next_steps": next_steps,
        "created_message": created_message,
        "error_message": error_message,
    }

    return render(request, "accounts/setup_wizard.html", context)
