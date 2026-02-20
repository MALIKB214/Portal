from collections import defaultdict

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
import base64
import io

from django.http import HttpResponse
from django.db.models import Sum, Count, F, IntegerField, ExpressionWrapper
from django.utils import timezone
from django.urls import reverse

from students.models import Student
from results.models import Result
from results.grading import pass_mark
from academics.models import Subject, AcademicSession, Term
from .forms import ContactMessageForm, SchoolBrandingForm
from .models import SchoolBranding
from .permissions import teacher_required, proprietor_required


def landing_page(request):
    brand = SchoolBranding.get_solo()
    contact_form = ContactMessageForm(request.POST or None)

    if request.method == "POST":
        if contact_form.is_valid():
            contact_form.save()
            messages.success(request, "Message sent. Our team will contact you shortly.")
            return redirect(f"{reverse('accounts:landing')}#contact")
        messages.error(request, "Please correct the contact form errors.")

    features = [
        "Three-term cumulative result processing with promotion logic",
        "Teacher class-lock and approval workflow (draft, submitted, approved)",
        "Printable WAEC-style result slips and broadsheets",
        "Manual billing, receipts, and payment approval trail",
        "Parent result portal with controlled release",
        "Audit trail for every score change",
    ]
    pricing = [
        {"name": "Starter", "price": "NGN 350,000", "desc": "Single-campus deployment + setup"},
        {"name": "Professional", "price": "NGN 600,000", "desc": "Deployment + training + branded reports"},
        {"name": "Enterprise", "price": "Custom", "desc": "Multi-campus rollout + support SLA"},
    ]

    return render(
        request,
        "accounts/landing.html",
        {
            "contact_form": contact_form,
            "features": features,
            "pricing": pricing,
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


def teacher_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_teacher:
                login(request, user)
                return redirect("accounts:teacher_dashboard")
            else:
                messages.error(request, "You are not authorized as a teacher")
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
        students_qs = Student.objects.filter(class_name=request.user.teacher_class.name)
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

def total_score_expression():
    return ExpressionWrapper(
        F("ca1") + F("ca2") + F("ca3") + F("project") + F("exam"),
        output_field=IntegerField(),
    )


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
    except Exception:
        invoices = []
        invoice_total_count = 0
        payment_total_count = 0

    promotion_summary = []
    if session:
        totals = list(
            Result.objects.filter(session=session)
            .values("student_id")
            .annotate(total=Sum(total_score_expression()))
            .order_by("-total")
        )
        student_map = Student.objects.in_bulk([row["student_id"] for row in totals])
        for row in totals:
            student = student_map.get(row["student_id"])
            if not student:
                continue
            promotion_summary.append(
                {
                    "student": student,
                    "average": round((row["total"] or 0) / 3, 2),
                }
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
                    if average > pass_mark():
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
                    if average > pass_mark():
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
        "invoice_status_counts": invoice_status_counts,
        "payment_status_counts": payment_status_counts,
        "invoice_total_count": invoice_total_count,
        "payment_total_count": payment_total_count,
        "pass_fail_analytics": pass_fail_analytics,
        "analytics_term": analytics_term,
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "class_top10": class_top10,
        "chart_pref_stacked": getattr(request.user, "analytics_chart_stacked", False),
        "chart_pref_legend": getattr(request.user, "analytics_chart_show_legend", True),
        "current_pass_mark": pass_mark(),
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
                if average > pass_mark():
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
                if average > pass_mark():
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
