from dataclasses import dataclass

from django.db.models import Count, ExpressionWrapper, F, IntegerField, Sum


@dataclass(frozen=True)
class GradePolicy:
    grade_a_min: int = 70
    grade_b_min: int = 60
    grade_c_min: int = 50
    grade_d_min: int = 45
    pass_mark: int = 45

    def grade_for(self, score: float) -> str:
        if score >= self.grade_a_min:
            return "A"
        if score >= self.grade_b_min:
            return "B"
        if score >= self.grade_c_min:
            return "C"
        if score >= self.grade_d_min:
            return "D"
        return "F"

    def pass_fail_for(self, score: float) -> str:
        # Business rule: 45 and below fail.
        return "PASS" if score > self.pass_mark else "FAIL"

    def key_text(self) -> str:
        return (
            f"A:{self.grade_a_min}-100  "
            f"B:{self.grade_b_min}-{self.grade_a_min - 1}  "
            f"C:{self.grade_c_min}-{self.grade_b_min - 1}  "
            f"D:{self.grade_d_min}-{self.grade_c_min - 1}  "
            f"F:0-{self.grade_d_min - 1}"
        )


@dataclass(frozen=True)
class PromotionPolicy:
    min_attendance_rate: float = 75.0
    min_behavior_average: float = 2.5
    require_non_cognitive: bool = True


def get_grade_policy() -> GradePolicy:
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        if brand.grading_template == SchoolBranding.GRADING_TEMPLATE_WAEC:
            return GradePolicy(
                grade_a_min=75,
                grade_b_min=65,
                grade_c_min=55,
                grade_d_min=45,
                pass_mark=45,
            )
        if brand.grading_template == SchoolBranding.GRADING_TEMPLATE_STRICT:
            return GradePolicy(
                grade_a_min=80,
                grade_b_min=70,
                grade_c_min=60,
                grade_d_min=50,
                pass_mark=50,
            )
        return GradePolicy(
            grade_a_min=brand.grade_a_min,
            grade_b_min=brand.grade_b_min,
            grade_c_min=brand.grade_c_min,
            grade_d_min=brand.grade_d_min,
            pass_mark=brand.pass_mark,
        )
    except Exception:
        return GradePolicy()


def grade_from_score(score: float) -> str:
    return get_grade_policy().grade_for(score)


def grade_key_text() -> str:
    return get_grade_policy().key_text()


def compute_pass_fail(score: float) -> str:
    return get_grade_policy().pass_fail_for(score)


def pass_mark() -> int:
    return get_grade_policy().pass_mark


def get_promotion_policy() -> PromotionPolicy:
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        return PromotionPolicy(
            min_attendance_rate=float(getattr(brand, "promotion_min_attendance_rate", 75.0)),
            min_behavior_average=float(getattr(brand, "promotion_min_behavior_average", 2.5)),
            require_non_cognitive=bool(
                getattr(brand, "promotion_require_non_cognitive", True)
            ),
        )
    except Exception:
        try:
            from django.conf import settings

            return PromotionPolicy(
                min_attendance_rate=float(
                    getattr(settings, "PROMOTION_MIN_ATTENDANCE_RATE", 75.0)
                ),
                min_behavior_average=float(
                    getattr(settings, "PROMOTION_MIN_BEHAVIOR_AVERAGE", 2.5)
                ),
                require_non_cognitive=bool(
                    getattr(settings, "PROMOTION_REQUIRE_NON_COGNITIVE", True)
                ),
            )
        except Exception:
            return PromotionPolicy()


def compute_promotion_decision(
    cumulative_average,
    attendance_rate=0.0,
    behavior_average=0.0,
    non_cognitive_count=0,
):
    policy = get_promotion_policy()
    if compute_pass_fail(cumulative_average) != "PASS":
        return "NOT PROMOTED", "Academic average below pass rule."

    if policy.require_non_cognitive and non_cognitive_count == 0:
        return "PENDING", "Attendance/behavior assessment not submitted."

    if attendance_rate < policy.min_attendance_rate:
        return (
            "NOT PROMOTED",
            f"Attendance rate {attendance_rate:.1f}% below {policy.min_attendance_rate:.0f}%.",
        )
    if behavior_average < policy.min_behavior_average:
        return (
            "NOT PROMOTED",
            f"Behavior score {behavior_average:.2f} below {policy.min_behavior_average:.2f}.",
        )
    return "PROMOTED", "Meets academic, attendance, and behavior criteria."


def total_score_expression():
    return ExpressionWrapper(
        F("ca1") + F("ca2") + F("exam"),
        output_field=IntegerField(),
    )


def ordinal(value):
    if value is None:
        return ""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    if 10 <= (value % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def compute_rankings(rows, total_key="total", ranking_policy="competition"):
    sorted_rows = sorted(rows, key=lambda x: x.get(total_key, 0), reverse=True)
    last_total = None
    current_rank = 0
    for idx, row in enumerate(sorted_rows, start=1):
        total = row.get(total_key, 0)
        if total != last_total:
            if ranking_policy == "dense":
                current_rank = current_rank + 1
            else:
                current_rank = idx
            last_total = total
        row["rank"] = current_rank
        row["rank_display"] = ordinal(current_rank)
    return sorted_rows


def compute_term_totals(session, term, student_ids):
    if not (session and term and student_ids):
        return {}
    from .models import Result

    rows = (
        Result.objects.filter(session=session, term=term, student_id__in=student_ids)
        .values("student_id")
        .annotate(
            total=Sum(total_score_expression()),
            count=Count("id"),
        )
    )
    data = {}
    for row in rows:
        total = row["total"] or 0
        count = row["count"] or 0
        data[row["student_id"]] = {
            "total": total,
            "count": count,
            "average": round(total / count, 2) if count else 0,
        }
    return data


def compute_session_cumulative(session, student_ids):
    if not (session and student_ids):
        return {}
    from .models import Result
    from academics.models import Term

    term_orders = list(Term.objects.filter(session=session).order_by("order").values_list("order", flat=True))
    rows = (
        Result.objects.filter(session=session, student_id__in=student_ids)
        .values("student_id", "term__order")
        .annotate(total=Sum(total_score_expression()))
    )

    per_student = {sid: {"term_totals": {order: 0 for order in term_orders}} for sid in student_ids}
    for row in rows:
        sid = row["student_id"]
        order = row["term__order"]
        if sid not in per_student:
            per_student[sid] = {"term_totals": {order: 0 for order in term_orders}}
        per_student[sid]["term_totals"][order] = row["total"] or 0

    divisor = 3 if 3 in term_orders else (len(term_orders) or 1)
    for sid, payload in per_student.items():
        cumulative_total = sum(payload["term_totals"].values())
        cumulative_average = round(cumulative_total / divisor, 2)
        payload["cumulative_total"] = cumulative_total
        payload["cumulative_average"] = cumulative_average
        payload["pass_fail"] = compute_pass_fail(cumulative_average)

    return per_student


def compute_student_session_snapshot(session, student_ids):
    if not (session and student_ids):
        return {}
    from .models import Result, StudentDomainAssessment
    from academics.models import Term

    session_terms = list(Term.objects.filter(session=session).order_by("order"))
    term_orders = [term.order for term in session_terms]
    rows = (
        Result.objects.filter(session=session, student_id__in=student_ids)
        .values("student_id", "term__order")
        .annotate(
            total=Sum(total_score_expression()),
            count=Count("id"),
        )
    )
    domain_rows = list(
        StudentDomainAssessment.objects.filter(session=session, student_id__in=student_ids)
        .values(
            "student_id",
            "discipline",
            "respect",
            "punctuality",
            "teamwork",
            "leadership",
            "moral_conduct",
            "handwriting",
            "sport",
            "laboratory_practical",
            "technical_drawing",
            "creative_arts",
            "computer_practical",
            "times_school_opened",
            "times_present",
            "times_absent",
        )
    )

    snapshot = {
        sid: {
            "term_totals": {order: 0 for order in term_orders},
            "term_counts": {order: 0 for order in term_orders},
            "term_averages": {order: 0 for order in term_orders},
            "cumulative_total": 0,
            "cumulative_average": 0,
            "pass_fail": "FAIL",
            "attendance_rate": 0.0,
            "behavior_average": 0.0,
            "psychomotor_average": 0.0,
            "promotion_status": "PENDING",
            "promotion_reason": "Awaiting evaluation.",
        }
        for sid in student_ids
    }

    for row in rows:
        sid = row["student_id"]
        order = row["term__order"]
        if sid not in snapshot:
            continue
        snapshot[sid]["term_totals"][order] = row["total"] or 0
        snapshot[sid]["term_counts"][order] = row["count"] or 0

    non_cognitive = {
        sid: {
            "opened": 0,
            "present": 0,
            "absent": 0,
            "behavior_sum": 0.0,
            "psychomotor_sum": 0.0,
            "count": 0,
        }
        for sid in student_ids
    }
    for row in domain_rows:
        sid = row["student_id"]
        if sid not in non_cognitive:
            continue
        bucket = non_cognitive[sid]
        bucket["opened"] += row.get("times_school_opened", 0) or 0
        bucket["present"] += row.get("times_present", 0) or 0
        bucket["absent"] += row.get("times_absent", 0) or 0
        behavior_values = [
            row.get("discipline", 0) or 0,
            row.get("respect", 0) or 0,
            row.get("punctuality", 0) or 0,
            row.get("teamwork", 0) or 0,
            row.get("leadership", 0) or 0,
            row.get("moral_conduct", 0) or 0,
        ]
        psychomotor_values = [
            row.get("handwriting", 0) or 0,
            row.get("sport", 0) or 0,
            row.get("laboratory_practical", 0) or 0,
            row.get("technical_drawing", 0) or 0,
            row.get("creative_arts", 0) or 0,
            row.get("computer_practical", 0) or 0,
        ]
        bucket["behavior_sum"] += sum(behavior_values) / len(behavior_values)
        bucket["psychomotor_sum"] += sum(psychomotor_values) / len(psychomotor_values)
        bucket["count"] += 1

    divisor = 3 if 3 in term_orders else (len(term_orders) or 1)
    for sid, payload in snapshot.items():
        for order in term_orders:
            total = payload["term_totals"].get(order, 0)
            count = payload["term_counts"].get(order, 0)
            payload["term_averages"][order] = round(total / count, 2) if count else 0
        cumulative_total = sum(payload["term_totals"].values())
        cumulative_average = round(cumulative_total / divisor, 2)
        payload["cumulative_total"] = cumulative_total
        payload["cumulative_average"] = cumulative_average
        payload["pass_fail"] = compute_pass_fail(cumulative_average)
        domain_payload = non_cognitive.get(sid, {})
        opened = domain_payload.get("opened", 0)
        present = domain_payload.get("present", 0)
        count = domain_payload.get("count", 0)
        behavior_average = (
            round(domain_payload.get("behavior_sum", 0.0) / count, 2) if count else 0.0
        )
        psychomotor_average = (
            round(domain_payload.get("psychomotor_sum", 0.0) / count, 2) if count else 0.0
        )
        attendance_rate = round((present / opened) * 100, 1) if opened else 0.0
        promotion_status, promotion_reason = compute_promotion_decision(
            cumulative_average=cumulative_average,
            attendance_rate=attendance_rate,
            behavior_average=behavior_average,
            non_cognitive_count=count,
        )
        payload["attendance_rate"] = attendance_rate
        payload["behavior_average"] = behavior_average
        payload["psychomotor_average"] = psychomotor_average
        payload["promotion_status"] = promotion_status
        payload["promotion_reason"] = promotion_reason
    return snapshot
