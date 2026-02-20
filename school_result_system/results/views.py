from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Sum, F, IntegerField, ExpressionWrapper, Avg, Count
from django.utils import timezone

from academics.models import AcademicSession, Term, Subject
from students.models import Student
from .models import Result, ResultRelease, Notification
from .utils import generate_result_pdf, generate_all_results_pdf
from .forms import ResultForm
from .grading import pass_mark
from accounts.permissions import teacher_required, teacher_with_class_required
from accounts.permissions import proprietor_required

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
    rows.sort(key=lambda x: x[total_key], reverse=True)
    rank = 0
    previous_total = None
    tied_count = 0
    for row in rows:
        current_total = row[total_key]
        if previous_total is None or current_total != previous_total:
            rank = rank + tied_count + 1
            tied_count = 0
        else:
            tied_count += 1
        row["rank"] = rank
        row["rank_display"] = ordinal(rank)
        previous_total = current_total
    return rows


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


def get_teacher_students(user):
    if getattr(user, "teacher_class", None):
        return Student.objects.filter(class_name=user.teacher_class.name)
    return Student.objects.none()

def total_score_expression():
    return ExpressionWrapper(
        F("ca1") + F("ca2") + F("ca3") + F("project") + F("exam"),
        output_field=IntegerField(),
    )


def build_term_totals_map(session, term, students_qs):
    if not (session and term and students_qs.exists()):
        return {}
    totals = (
        Result.objects.filter(session=session, term=term, student__in=students_qs)
        .values("student_id")
        .annotate(total=Sum(total_score_expression()))
    )
    return {row["student_id"]: row["total"] or 0 for row in totals}


def build_session_totals_map(session, students_qs):
    if not (session and students_qs.exists()):
        return {}
    totals = (
        Result.objects.filter(session=session, student__in=students_qs)
        .values("student_id")
        .annotate(total=Sum(total_score_expression()))
    )
    return {row["student_id"]: row["total"] or 0 for row in totals}

def build_term_totals_map_for_ids(session, term, student_ids):
    if not (session and term and student_ids):
        return {}
    totals = (
        Result.objects.filter(session=session, term=term, student_id__in=student_ids)
        .values("student_id")
        .annotate(total=Sum(total_score_expression()))
    )
    return {row["student_id"]: row["total"] or 0 for row in totals}


def build_session_totals_map_for_ids(session, student_ids):
    if not (session and student_ids):
        return {}
    totals = (
        Result.objects.filter(session=session, student_id__in=student_ids)
        .values("student_id")
        .annotate(total=Sum(total_score_expression()))
    )
    return {row["student_id"]: row["total"] or 0 for row in totals}


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

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
    except Exception:
        return render(
            request,
            "results/broadsheet.html",
            {"error": "PDF export requires reportlab. Install it and retry."},
        )

    filename = f"broadsheet_{session}_{term}.pdf".replace(" ", "_")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, f"Broadsheet - {session} - {term}")
    y -= 20
    pdf.setFont("Helvetica", 8)
    col_widths = [120] + [40 for _ in subjects] + [50, 50, 50]
    headers = ["Student"] + [s.name for s in subjects] + ["Total", "Average", "Pos"]
    x = 40
    for width, header in zip(col_widths, headers):
        pdf.drawString(x + 2, y, header)
        x += width
    y -= 12
    for row in students_data:
        if y < 50:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 8)
        x = 40
        values = [row["student"].full_name]
        for subject in subjects:
            values.append(str(row["subjects"].get(subject.id, "")))
        values += [row["total"], row["average"], row["rank_display"]]
        for width, value in zip(col_widths, values):
            pdf.drawString(x + 2, y, str(value))
            x += width
        y -= 10

    pdf.showPage()
    pdf.save()
    return response


@proprietor_required
def release_results(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    session = get_active_session()
    term = get_active_term(session)
    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    if request.method == "POST":
        action = request.POST.get("action", "release")
        session_id = request.POST.get("session")
        term_id = request.POST.get("term")
        class_name = (request.POST.get("class_name") or "").strip()
        session = AcademicSession.objects.filter(id=session_id).first()
        term = Term.objects.filter(id=term_id, session=session).first()

        if not session or not term:
            messages.error(request, "Session and term are required.")
        else:
            scoped_results = _scoped_results(session, term, class_name)

            if action == "approve":
                updated = scoped_results.filter(status=Result.STATUS_SUBMITTED).update(
                    status=Result.STATUS_APPROVED,
                    approved_by=request.user,
                    approved_at=timezone.now(),
                    updated_by=request.user,
                    updated_at=timezone.now(),
                )
                if updated:
                    messages.success(request, f"{updated} result entries approved.")
                else:
                    messages.info(request, "No submitted results found to approve.")
            else:
                if not scoped_results.exists():
                    messages.error(request, "No results found for selected scope.")
                else:
                    unapproved = scoped_results.exclude(status=Result.STATUS_APPROVED).count()
                    if unapproved:
                        messages.error(
                            request,
                            f"Cannot release yet. {unapproved} result entries are not approved.",
                        )
                    else:
                        release, created = ResultRelease.objects.get_or_create(
                            session=session,
                            term=term,
                            class_name=class_name,
                            defaults={"released_by": request.user},
                        )
                        if not created:
                            messages.info(request, "Results already released for this selection.")
                        else:
                            students_qs = Student.objects.all()
                            if class_name:
                                students_qs = students_qs.filter(class_name=class_name)
                            notifications = [
                                Notification(
                                    student=student,
                                    session=session,
                                    term=term,
                                    message=f"Your result for {term} has been released.",
                                )
                                for student in students_qs
                            ]
                            Notification.objects.bulk_create(notifications)
                            messages.success(request, "Results released and notifications created.")

    summary = {}
    if session and term:
        scoped_results = _scoped_results(session, term)
        summary = {
            "total": scoped_results.count(),
            "draft": scoped_results.filter(status=Result.STATUS_DRAFT).count(),
            "submitted": scoped_results.filter(status=Result.STATUS_SUBMITTED).count(),
            "approved": scoped_results.filter(status=Result.STATUS_APPROVED).count(),
        }

    context = {
        "sessions": sessions,
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
        "summary": summary,
    }
    return render(request, "results/release_results.html", context)

def ensure_teacher_class(request):
    if not getattr(request.user, "teacher_class", None):
        return render(request, "accounts/no_class_assigned.html")
    return None


def _scoped_results(session, term, class_name=""):
    queryset = Result.objects.filter(session=session, term=term)
    if class_name:
        queryset = queryset.filter(student__class_name=class_name)
    return queryset


def _can_view_released_result(student, session, term):
    return ResultRelease.objects.filter(
        session=session,
        term=term,
        class_name__in=["", student.class_name or ""],
    ).exists()


def parent_portal_login(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    terms = Term.objects.select_related("session").order_by("session__name", "order")

    if request.method == "POST":
        admission_number = (request.POST.get("admission_number") or "").strip()
        parent_surname = (request.POST.get("parent_surname") or "").strip().lower()
        student = Student.objects.filter(admission_number=admission_number).first()

        if not student:
            messages.error(request, "Invalid admission number.")
        elif (student.last_name or "").strip().lower() != parent_surname:
            messages.error(request, "Surname does not match our record.")
        else:
            request.session["parent_student_id"] = student.id
            return redirect("results:parent_portal")

    return render(
        request,
        "results/parent_login.html",
        {"sessions": sessions, "terms": terms},
    )


def parent_portal_logout(request):
    request.session.pop("parent_student_id", None)
    return redirect("results:parent_login")


def parent_portal(request):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        return redirect("results:parent_login")

    student = get_object_or_404(Student, id=student_id)
    session = get_active_session()
    term = get_active_term(session)

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = get_active_term(session)
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    results = (
        Result.objects.filter(student=student, session=session, term=term)
        .select_related("subject")
        .order_by("subject__name")
    )

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

    if show_cumulative:
        term_totals_data = (
            Result.objects.filter(student=student, session=session)
            .values("term__order")
            .annotate(total=Sum(total_score_expression()))
        )
        for row in term_totals_data:
            term_totals[row["term__order"]] = row["total"] or 0
        cumulative_total = sum(term_totals.values())
        cumulative_average = round(cumulative_total / 3, 2)
        pass_fail = "PASS" if cumulative_average > pass_mark() else "FAIL"

    return render(
        request,
        "results/parent_portal.html",
        {
            "student": student,
            "results": results,
            "sessions": AcademicSession.objects.all().order_by("-id"),
            "terms": Term.objects.filter(session=session).order_by("order") if session else [],
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
        },
    )


def check_result(request):
    sessions = AcademicSession.objects.all().order_by("-id")
    terms = Term.objects.select_related("session").order_by("session__name", "order")

    if request.method == "POST":
        reg_no = request.POST.get("admission_number")
        session_id = request.POST.get("session")
        term_id = request.POST.get("term")

        student = Student.objects.filter(admission_number=reg_no).first()
        session = AcademicSession.objects.filter(id=session_id).first()
        term = Term.objects.filter(id=term_id, session=session).first()

        if not student or not session or not term:
            return render(
                request,
                "results/check.html",
                {
                    "error": "Result not found for the selected session/term.",
                    "sessions": sessions,
                    "terms": terms,
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
                },
            )

        results = (
            Result.objects.filter(student=student, session=session, term=term)
            .select_related("subject")
            .order_by("subject__name")
        )

        term_total = sum(result.total_score for result in results)
        average = round(term_total / results.count(), 2) if results.exists() else 0

        session_terms = Term.objects.filter(session=session).order_by("order")
        term_totals_map = {
            row["term__order"]: row["total"] or 0
            for row in Result.objects.filter(student=student, session=session)
            .values("term__order")
            .annotate(total=Sum(total_score_expression()))
        }
        session_term_totals = [
            {"term": session_term, "total": term_totals_map.get(session_term.order, 0)}
            for session_term in session_terms
        ]
        session_term_averages = []
        for session_term in session_terms:
            term_results = Result.objects.filter(
                student=student, session=session, term=session_term
            )
            term_total = term_totals_map.get(session_term.order, 0)
            term_avg = round(term_total / term_results.count(), 2) if term_results.exists() else 0
            session_term_averages.append({"term": session_term, "average": term_avg})

        promotion_average = (
            round(sum(item["total"] for item in session_term_totals) / 3, 2)
            if session_term_totals
            else 0
        )
        cumulative_total = sum(item["total"] for item in session_term_totals)
        cumulative_average = round(cumulative_total / 3, 2) if session_term_totals else 0

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
                "cumulative_rank_display": session_rank_display,
                "term_rank": term_rank,
                "session_rank": session_rank,
                "term_rank_display": term_rank_display,
                "session_rank_display": session_rank_display,
                "release_info": release_info,
            },
        )

    return render(
        request,
        "results/check.html",
        {
            "sessions": sessions,
            "terms": terms,
        },
    )


def download_result_pdf(request, student_id, session_id, term_id):
    student = get_object_or_404(Student, id=student_id)
    session = get_object_or_404(AcademicSession, id=session_id)
    term = get_object_or_404(Term, id=term_id, session=session)
    results = Result.objects.filter(student=student, session=session, term=term)
    summary = None
    position_display = ""

    class_student_ids = list(
        Student.objects.filter(class_name=student.class_name).values_list("id", flat=True)
    )
    if term.order == 3:
        session_terms = Term.objects.filter(session=session).order_by("order")
        term_totals = {1: 0, 2: 0, 3: 0}
        totals_map = {
            row["term__order"]: row["total"] or 0
            for row in Result.objects.filter(student=student, session=session)
            .values("term__order")
            .annotate(total=Sum(total_score_expression()))
        }
        cumulative_total = 0
        for session_term in session_terms:
            term_total = totals_map.get(session_term.order, 0)
            term_totals[session_term.order] = term_total
            cumulative_total += term_total
        cumulative_average = round(cumulative_total / 3, 2) if session_terms else 0

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

        pass_fail = "FAIL" if cumulative_average <= pass_mark() else "PASS"

        summary = {
            "term1_total": term_totals.get(1, ""),
            "term2_total": term_totals.get(2, ""),
            "term3_total": term_totals.get(3, ""),
            "cumulative_total": cumulative_total,
            "cumulative_average": cumulative_average,
            "pass_fail": pass_fail,
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
        student, results, session, term, summary, position=position_display
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

    subjects = Subject.objects.all().order_by("name")
    students = list(Student.objects.all().order_by("last_name", "first_name"))
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
        session_terms = Term.objects.filter(session=session).order_by("order")
        term_totals_rows = (
            Result.objects.filter(
                session=session, term__in=session_terms, student_id__in=student_ids
            )
            .values("student_id", "term__order")
            .annotate(total=Sum(total_score_expression()))
        )
        totals_map = defaultdict(dict)
        for row in term_totals_rows:
            totals_map[row["student_id"]][row["term__order"]] = row["total"] or 0

        for data in students_data:
            student_id = data["student"].id
            session_total = 0
            term_totals = {}
            for session_term in session_terms:
                term_total = totals_map.get(student_id, {}).get(session_term.order, 0)
                term_totals[session_term.order] = term_total
                session_total += term_total
            data["cumulative_total"] = session_total
            data["cumulative_average"] = round(session_total / 3, 2) if session_terms else 0
            data["term_totals"] = term_totals
            data["pass_fail"] = "FAIL" if data["cumulative_average"] <= pass_mark() else "PASS"

    rank_students(students_data, total_key="cumulative_total" if show_cumulative else "total")

    title = f"Results Sheet - {session} - {term}"
    return generate_all_results_pdf(title, subjects, students_data, show_cumulative=show_cumulative)


@teacher_with_class_required
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

    updated = scoped_results.filter(status=Result.STATUS_DRAFT).update(
        status=Result.STATUS_SUBMITTED,
        submitted_by=request.user,
        submitted_at=timezone.now(),
        updated_by=request.user,
        updated_at=timezone.now(),
    )
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
        cumulative_total = 0
        all_term_results = (
            Result.objects.filter(student=student, session=session, term__in=session_terms)
            .select_related("subject", "term")
        )
        for result in all_term_results:
            term_totals[result.term.order] = term_totals.get(result.term.order, 0) + result.total_score
            subject_term_scores.setdefault(result.subject_id, {})[
                result.term.order
            ] = result.total_score
            subject_term_cum[result.subject_id] = subject_term_cum.get(
                result.subject_id, 0
            ) + result.total_score
        cumulative_total = sum(term_totals.values())
        cumulative_average = round(cumulative_total / 3, 2) if session_terms else 0
        for session_term in session_terms:
            term_results = Result.objects.filter(
                student=student, session=session, term=session_term
            )
            term_total = term_totals.get(session_term.order, 0)
            term_averages[session_term.order] = (
                round(term_total / term_results.count(), 2) if term_results.exists() else 0
            )

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
            cumulative_total = sum(term_total_map.values()) if term_total_map else 0
            cumulative_average = round(cumulative_total / 3, 2) if session_terms else 0

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
    session_totals = build_session_totals_map_for_ids(session, student_ids)
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
