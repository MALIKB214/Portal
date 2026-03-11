from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from academics.models import SchoolClass
from students.models import Student
from .models import (
    Notification,
    Result,
    ResultRelease,
    ResultReopenLog,
    ResultWorkflow,
    ResultSnapshot,
)
from .snapshot_service import (
    create_or_refresh_snapshot,
    invalidate_snapshot,
    require_valid_snapshot,
)


def _scoped_results(session, term, school_class=None):
    qs = Result.objects.filter(session=session, term=term)
    if school_class:
        qs = qs.filter(
            Q(student__school_class=school_class)
            | Q(student__school_class__name__iexact=school_class.name)
            | Q(student__school_class__isnull=True, student__class_name__iexact=school_class.name)
        )
    return qs


def _scoped_students(school_class=None):
    qs = Student.objects.all()
    if school_class:
        qs = qs.filter(
            Q(school_class=school_class)
            | Q(school_class__name__iexact=school_class.name)
            | Q(school_class__isnull=True, class_name__iexact=school_class.name)
        )
    return qs


def _classes_from_results(results_qs):
    class_ids = list(
        results_qs.exclude(student__school_class__isnull=True)
        .values_list("student__school_class_id", flat=True)
        .distinct()
    )
    classes = list(SchoolClass.objects.filter(id__in=class_ids))
    name_set = {
        name.strip()
        for name in results_qs.filter(student__school_class__isnull=True)
        .exclude(student__class_name__isnull=True)
        .exclude(student__class_name="")
        .values_list("student__class_name", flat=True)
    }
    for name in name_set:
        school_class = SchoolClass.objects.filter(name__iexact=name).first()
        if school_class and school_class.id not in class_ids:
            classes.append(school_class)
    return classes


def submit_results_for_class(session, term, school_class, user):
    with transaction.atomic():
        workflow, _ = ResultWorkflow.objects.get_or_create(
            session=session,
            term=term,
            school_class=school_class,
            defaults={"status": ResultWorkflow.STATUS_DRAFT},
        )
        if workflow.status in {ResultWorkflow.STATUS_APPROVED, ResultWorkflow.STATUS_RELEASED}:
            raise ValueError("This class workflow is locked and cannot be submitted.")

        scoped_results = _scoped_results(session, term, school_class=school_class)
        if not scoped_results.exists():
            raise ValueError("No results found for your class in this term.")

        updated = scoped_results.filter(status=Result.STATUS_DRAFT).update(
            status=Result.STATUS_SUBMITTED,
            submitted_by=user,
            submitted_at=timezone.now(),
            updated_by=user,
            updated_at=timezone.now(),
        )

        workflow.status = ResultWorkflow.STATUS_SUBMITTED
        workflow.submitted_by = user
        workflow.submitted_at = timezone.now()
        workflow.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
        return updated


def approve_results(session, term, user, school_class=None):
    with transaction.atomic():
        scoped_results = _scoped_results(session, term, school_class=school_class)
        if not scoped_results.exists():
            raise ValueError("No results found for selected scope.")

        target_classes = [school_class] if school_class else _classes_from_results(scoped_results)
        workflows = []
        for cls in target_classes:
            wf, _ = ResultWorkflow.objects.get_or_create(
                session=session,
                term=term,
                school_class=cls,
                defaults={"status": ResultWorkflow.STATUS_DRAFT},
            )
            if wf.status == ResultWorkflow.STATUS_RELEASED:
                raise ValueError("Cannot approve after release.")
            workflows.append(wf)

        submitted_qs = scoped_results.filter(status=Result.STATUS_SUBMITTED)
        updated = submitted_qs.update(
            status=Result.STATUS_APPROVED,
            approved_by=user,
            approved_at=timezone.now(),
            updated_by=user,
            updated_at=timezone.now(),
        )
        if updated == 0:
            return 0

        for wf in workflows:
            approved_in_class = _scoped_results(session, term, school_class=wf.school_class).filter(
                status=Result.STATUS_APPROVED
            )
            if not approved_in_class.exists():
                continue
            wf.status = ResultWorkflow.STATUS_APPROVED
            wf.approved_by = user
            wf.approved_at = timezone.now()
            wf.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
            create_or_refresh_snapshot(
                session=session,
                term=term,
                school_class=wf.school_class,
                approved_by=user,
                workflow=wf,
            )
        return updated


def release_results(session, term, user, school_class=None):
    with transaction.atomic():
        scoped_results = _scoped_results(session, term, school_class=school_class)
        if not scoped_results.exists():
            raise ValueError("No results found for selected scope.")

        unapproved = scoped_results.exclude(status=Result.STATUS_APPROVED).count()
        if unapproved:
            raise ValueError(f"Cannot release yet. {unapproved} result entries are not approved.")

        target_classes = [school_class] if school_class else _classes_from_results(scoped_results)
        workflows = []
        for cls in target_classes:
            wf, _ = ResultWorkflow.objects.get_or_create(
                session=session,
                term=term,
                school_class=cls,
                defaults={"status": ResultWorkflow.STATUS_DRAFT},
            )
            if wf.status not in {ResultWorkflow.STATUS_APPROVED, ResultWorkflow.STATUS_RELEASED}:
                raise ValueError("Cannot release yet. Workflow must be approved first.")
            require_valid_snapshot(session=session, term=term, school_class=cls)
            workflows.append(wf)

        release_class_name = school_class.name if school_class else ""
        release, created = ResultRelease.objects.get_or_create(
            session=session,
            term=term,
            class_name=release_class_name,
            defaults={"released_by": user},
        )
        if not created:
            return False, 0

        students_qs = _scoped_students(school_class=school_class)
        notifications = [
            Notification(
                student=student,
                session=session,
                term=term,
                category=Notification.CATEGORY_RESULTS,
                message=f"Your result for {term} ({session}) has been released.",
            )
            for student in students_qs
        ]
        Notification.objects.bulk_create(notifications)

        for wf in workflows:
            wf.status = ResultWorkflow.STATUS_RELEASED
            wf.released_by = user
            wf.released_at = timezone.now()
            wf.save(update_fields=["status", "released_by", "released_at", "updated_at"])

        return True, len(notifications)


def reopen_results(session, term, user, school_class=None, reason="Reopened for correction."):
    with transaction.atomic():
        scoped_results = _scoped_results(session, term, school_class=school_class)
        if not scoped_results.exists():
            raise ValueError("No results found for selected scope.")

        target_classes = [school_class] if school_class else _classes_from_results(scoped_results)

        if school_class:
            global_release_exists = ResultRelease.objects.filter(
                session=session, term=term, class_name=""
            ).exists()
            if global_release_exists:
                raise ValueError(
                    "This term was released globally. Reopen all classes together."
                )
            deleted_releases = ResultRelease.objects.filter(
                session=session, term=term, class_name=school_class.name
            ).delete()[0]
        else:
            deleted_releases = ResultRelease.objects.filter(session=session, term=term).delete()[0]

        reopened_results = scoped_results.filter(
            status__in=[Result.STATUS_SUBMITTED, Result.STATUS_APPROVED]
        ).update(
            status=Result.STATUS_DRAFT,
            submitted_by=None,
            submitted_at=None,
            approved_by=None,
            approved_at=None,
            updated_by=user,
            updated_at=timezone.now(),
        )

        for cls in target_classes:
            wf, _ = ResultWorkflow.objects.get_or_create(
                session=session,
                term=term,
                school_class=cls,
                defaults={"status": ResultWorkflow.STATUS_DRAFT},
            )
            wf.status = ResultWorkflow.STATUS_DRAFT
            wf.submitted_by = None
            wf.approved_by = None
            wf.released_by = None
            wf.submitted_at = None
            wf.approved_at = None
            wf.released_at = None
            wf.save(
                update_fields=[
                    "status",
                    "submitted_by",
                    "approved_by",
                    "released_by",
                    "submitted_at",
                    "approved_at",
                    "released_at",
                    "updated_at",
                ]
            )

            snapshot = ResultSnapshot.objects.filter(
                session=session, term=term, school_class=cls
            ).first()
            previous_hash = ""
            if snapshot:
                previous_hash = snapshot.content_hash
                invalidate_snapshot(snapshot, user=user, reason=reason)
            ResultReopenLog.objects.create(
                session=session,
                term=term,
                school_class=cls,
                reopened_by=user if getattr(user, "is_authenticated", False) else None,
                reason=reason,
                previous_hash=previous_hash,
            )

        return reopened_results, deleted_releases
