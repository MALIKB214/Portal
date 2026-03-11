import hashlib
import hmac
import json

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Result, ResultSnapshot, StudentDomainAssessment


def _serialize_payload(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload):
    return hashlib.sha256(_serialize_payload(payload).encode("utf-8")).hexdigest()


def _sign_hash(content_hash):
    secret = (settings.SECRET_KEY or "").encode("utf-8")
    return hmac.new(secret, content_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def _scoped_result_queryset(session, term, school_class):
    return Result.objects.filter(session=session, term=term).filter(
        Q(student__school_class=school_class)
        | Q(student__school_class__isnull=True, student__class_name=school_class.name)
    )


def _scoped_domain_queryset(session, term, school_class):
    return StudentDomainAssessment.objects.filter(session=session, term=term).filter(
        Q(student__school_class=school_class)
        | Q(student__school_class__isnull=True, student__class_name=school_class.name)
    )


def build_snapshot_payload(session, term, school_class):
    results = (
        _scoped_result_queryset(session, term, school_class)
        .select_related("student", "subject")
        .order_by("student_id", "subject_id")
    )
    domains = _scoped_domain_queryset(session, term, school_class).order_by("student_id")

    payload = {
        "session_id": session.id,
        "term_id": term.id,
        "school_class_id": school_class.id,
        "school_class_name": school_class.name,
        "results": [
            {
                "student_id": row.student_id,
                "subject_id": row.subject_id,
                "ca1": row.ca1,
                "ca2": row.ca2,
                "exam": row.exam,
                "total_score": row.total_score,
                "status": row.status,
            }
            for row in results
        ],
        "domains": [
            {
                "student_id": row.student_id,
                "discipline": row.discipline,
                "respect": row.respect,
                "punctuality": row.punctuality,
                "teamwork": row.teamwork,
                "leadership": row.leadership,
                "moral_conduct": row.moral_conduct,
                "handwriting": row.handwriting,
                "sport": row.sport,
                "laboratory_practical": row.laboratory_practical,
                "technical_drawing": row.technical_drawing,
                "creative_arts": row.creative_arts,
                "computer_practical": row.computer_practical,
                "times_school_opened": row.times_school_opened,
                "times_present": row.times_present,
                "times_absent": row.times_absent,
                "teacher_remark": row.teacher_remark,
                "principal_remark": row.principal_remark,
                "next_term_begins": row.next_term_begins,
            }
            for row in domains
        ],
    }
    return payload


def create_or_refresh_snapshot(session, term, school_class, approved_by=None, workflow=None):
    payload = build_snapshot_payload(session, term, school_class)
    content_hash = _payload_hash(payload)
    signature = _sign_hash(content_hash)

    snapshot, _ = ResultSnapshot.objects.update_or_create(
        session=session,
        term=term,
        school_class=school_class,
        defaults={
            "workflow": workflow,
            "approved_by": approved_by,
            "approved_at": timezone.now(),
            "payload": payload,
            "content_hash": content_hash,
            "signature": signature,
            "verified_at": timezone.now(),
            "invalidated_at": None,
            "invalidated_by": None,
            "invalidation_reason": "",
        },
    )
    return snapshot


def verify_snapshot(snapshot):
    payload = build_snapshot_payload(snapshot.session, snapshot.term, snapshot.school_class)
    recalculated_hash = _payload_hash(payload)
    expected_signature = _sign_hash(recalculated_hash)
    hash_valid = recalculated_hash == snapshot.content_hash
    signature_valid = expected_signature == snapshot.signature
    is_valid = bool(hash_valid and signature_valid and not snapshot.invalidated_at)
    if is_valid:
        snapshot.verified_at = timezone.now()
        snapshot.save(update_fields=["verified_at", "updated_at"])
    reason = ""
    if snapshot.invalidated_at:
        reason = "Snapshot invalidated by reopen action."
    elif not hash_valid:
        reason = "Snapshot hash mismatch. Result data changed after approval."
    elif not signature_valid:
        reason = "Snapshot signature mismatch."
    return is_valid, reason, recalculated_hash


def require_valid_snapshot(session, term, school_class):
    snapshot = ResultSnapshot.objects.filter(
        session=session, term=term, school_class=school_class
    ).first()
    if not snapshot:
        raise ValueError(f"No approval snapshot found for {school_class}.")
    is_valid, reason, _ = verify_snapshot(snapshot)
    if not is_valid:
        raise ValueError(f"Snapshot verification failed for {school_class}: {reason}")
    return snapshot


def invalidate_snapshot(snapshot, user=None, reason="Reopened for correction."):
    snapshot.invalidated_at = timezone.now()
    snapshot.invalidated_by = user if getattr(user, "is_authenticated", False) else None
    snapshot.invalidation_reason = reason
    snapshot.save(
        update_fields=[
            "invalidated_at",
            "invalidated_by",
            "invalidation_reason",
            "updated_at",
        ]
    )
    return snapshot
