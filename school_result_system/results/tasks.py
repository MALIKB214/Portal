from celery import shared_task

from django.db import models

from academics.models import AcademicSession, Term
from results.notifications import (
    format_result_release_email,
    notify_parent_event,
)
from results.models import Notification, ResultRelease, ResultWorkflow
from students.models import Student
from accounts.models import User, StaffNotification
from accounts.notifications import notify_staff_event


@shared_task
def send_release_notifications_task(session_id, term_id, class_name=""):
    session = AcademicSession.objects.filter(id=session_id).first()
    term = Term.objects.filter(id=term_id, session_id=session_id).first()
    if not session or not term:
        return

    release = ResultRelease.objects.filter(session=session, term=term, class_name=class_name).first()
    if not release:
        return

    students_qs = Student.objects.filter(class_name=class_name) if class_name else Student.objects.all()
    for student in students_qs:
        subject, body = format_result_release_email(student, term, session)
        notify_parent_event(
            student,
            f"Your result for {term} ({session}) has been released.",
            session=session,
            term=term,
            category=Notification.CATEGORY_RESULTS,
            send_email=True,
            email_subject=subject,
            email_body=body,
        )


def _results_recipients():
    return (
        User.objects.filter(
            models.Q(is_proprietor=True)
            | models.Q(is_admin=True)
            | models.Q(is_superuser=True)
            | models.Q(groups__name__in=["Principal"])
        )
        .distinct()
        .only("id", "username", "email", "first_name", "last_name")
    )


@shared_task
def send_release_reminders_task(session_id=None, term_id=None, notify_user_id=None):
    qs = ResultWorkflow.objects.all()
    if session_id:
        qs = qs.filter(session_id=session_id)
    if term_id:
        qs = qs.filter(term_id=term_id)

    submitted_count = qs.filter(status=ResultWorkflow.STATUS_SUBMITTED).count()
    approved_count = qs.filter(status=ResultWorkflow.STATUS_APPROVED).count()

    if submitted_count == 0 and approved_count == 0:
        return

    scope = []
    if session_id:
        session_obj = AcademicSession.objects.filter(id=session_id).first()
        scope.append(f"session {session_obj or session_id}")
    if term_id:
        term_obj = Term.objects.filter(id=term_id).first()
        scope.append(f"term {term_obj or term_id}")
    scope_label = f" ({', '.join(scope)})" if scope else ""

    message = (
        "Result workflow reminder: "
        f"{submitted_count} class(es) submitted awaiting approval, "
        f"{approved_count} class(es) approved awaiting release.{scope_label}"
    )
    subject = "Result Release Reminder"
    if scope:
        subject += f" {scope_label}"
    email_body = (
        "Result workflow reminder\n\n"
        f"Submitted awaiting approval: {submitted_count}\n"
        f"Approved awaiting release: {approved_count}\n\n"
        "Please review in the staff portal."
    )

    recipients = _results_recipients()
    if notify_user_id:
        recipients = recipients.filter(id=notify_user_id)

    for user in recipients:
        notify_staff_event(
            user,
            message,
            category=StaffNotification.CATEGORY_RESULTS,
            email_subject=subject,
            email_body=email_body,
            send_email=True,
        )
