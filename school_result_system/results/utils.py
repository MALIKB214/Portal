from django.conf import settings
from django.http import HttpResponse
from .grading import grade_key_text


def _draw_school_badge(pdf, x, y, school_logo=None):
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader

    if school_logo:
        try:
            image = ImageReader(school_logo.path)
            pdf.drawImage(image, x - 16, y - 16, width=32, height=32, mask="auto")
            return
        except Exception:
            pass

    pdf.setStrokeColor(colors.HexColor("#0b5d67"))
    pdf.setFillColor(colors.HexColor("#0b5d67"))
    pdf.circle(x, y, 16, stroke=1, fill=0)
    pdf.circle(x, y, 12, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(x, y - 3, "AW")


def _draw_table(pdf, x, y, col_widths, headers, rows, row_height=16, page_size=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4

    if page_size is None:
        page_size = A4

    pdf.setStrokeColor(colors.HexColor("#9ca3af"))
    pdf.setLineWidth(0.6)
    total_width = sum(col_widths)

    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.rect(x, y - row_height + 2, total_width, row_height, fill=1, stroke=0)
    pdf.setFillColor(colors.white)

    cursor_x = x + 4
    for width, header in zip(col_widths, headers):
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(cursor_x, y - row_height + 7, str(header))
        cursor_x += width

    current_y = y - row_height
    pdf.setFillColor(colors.black)
    for index, row in enumerate(rows):
        current_y -= row_height
        if index % 2 == 0:
            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.rect(x, current_y, total_width, row_height, fill=1, stroke=0)
            pdf.setFillColor(colors.black)

        cursor_x = x + 4
        for width, cell in zip(col_widths, row):
            text = str(cell)
            if len(text) > 28:
                text = f"{text[:25]}..."
            pdf.setFont("Helvetica", 8)
            pdf.drawString(cursor_x, current_y + 5, text)
            cursor_x += width
        pdf.line(x, current_y, x + total_width, current_y)

        if current_y < 90:
            pdf.showPage()
            current_y = page_size[1] - 90
    return current_y


def _grade_key():
    return grade_key_text()


def generate_result_pdf(student, results, session, term, summary=None, position=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{student.admission_number}_result.pdf"'
    )

    school_name = getattr(settings, "SCHOOL_NAME", "Al-Waarith Model College")
    school_motto = getattr(settings, "SCHOOL_MOTTO", "Results and Records Portal")
    principal_name = getattr(settings, "SCHOOL_PRINCIPAL_NAME", "Principal")
    class_teacher_name = getattr(settings, "SCHOOL_CLASS_TEACHER_NAME", "Class Teacher")
    school_logo = None
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        school_name = brand.school_name or school_name
        school_motto = brand.school_motto or school_motto
        principal_name = brand.principal_signature_name or principal_name
        class_teacher_name = brand.class_teacher_signature_name or class_teacher_name
        school_logo = brand.school_logo if brand.school_logo else None
    except Exception:
        pass

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    is_third_term = bool(term and getattr(term, "order", None) == 3)

    y = height - 45
    _draw_school_badge(pdf, 66, y - 2, school_logo=school_logo)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(92, y + 5, school_name)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#374151"))
    pdf.drawString(92, y - 10, school_motto)
    pdf.setFillColor(colors.black)
    pdf.setStrokeColor(colors.HexColor("#111827"))
    pdf.line(45, y - 20, width - 45, y - 20)

    y -= 44
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(width / 2, y, "STUDENT RESULT SLIP")

    y -= 24
    pdf.setFont("Helvetica", 9)
    pdf.drawString(45, y, f"Name: {student.full_name}")
    pdf.drawString(305, y, f"Admission No: {student.admission_number}")
    y -= 14
    pdf.drawString(45, y, f"Class: {student.class_name or '-'}")
    pdf.drawString(305, y, f"Session: {session}")
    y -= 14
    pdf.drawString(45, y, f"Term: {term}")
    pdf.drawString(305, y, f"Position: {summary.get('position', '') if summary else (position or '')}")

    y -= 20
    headers = ["Subject", "CA1", "CA2", "CA3", "Proj", "Exam", "Total", "Grade"]
    col_widths = [170, 36, 36, 36, 42, 42, 46, 44]
    rows = [
        [
            str(result.subject),
            result.ca1,
            result.ca2,
            result.ca3,
            result.project,
            result.exam,
            result.total_score,
            result.grade(),
        ]
        for result in results
    ]
    y = _draw_table(pdf, 45, y, col_widths, headers, rows, row_height=16, page_size=A4)

    term_total = sum(result.total_score for result in results)
    subject_count = len(rows)
    term_average = round(term_total / subject_count, 2) if subject_count else 0

    y -= 16
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(45, y, f"Term Total: {term_total}")
    pdf.drawString(180, y, f"Term Average: {term_average}")
    pdf.drawString(330, y, f"Position: {summary.get('position', '') if summary else (position or '')}")

    if is_third_term and summary:
        y -= 18
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(45, y, "Cumulative Summary (Promotion Basis)")
        y -= 14
        pdf.setFont("Helvetica", 9)
        pdf.drawString(45, y, f"T1: {summary.get('term1_total', 0)}")
        pdf.drawString(125, y, f"T2: {summary.get('term2_total', 0)}")
        pdf.drawString(205, y, f"T3: {summary.get('term3_total', 0)}")
        pdf.drawString(285, y, f"Cumulative Total: {summary.get('cumulative_total', 0)}")
        pdf.drawString(445, y, f"Cumulative Avg: {summary.get('cumulative_average', 0)}")
        y -= 14
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(45, y, f"Decision: {summary.get('pass_fail', '')}")
        pdf.drawString(180, y, f"Cumulative Position: {summary.get('position', '')}")

    # Remarks and grading key
    y -= 18
    pass_fail = summary.get("pass_fail", "") if summary else ""
    remark = "Promoted" if (is_third_term and pass_fail == "PASS") else "Not Promoted"
    if not is_third_term:
        remark = "Academic performance recorded."
    pdf.setFont("Helvetica", 9)
    pdf.drawString(45, y, f"Remark: {remark}")
    y -= 12
    pdf.drawString(45, y, f"Grading Key: {_grade_key()}")

    # Signature lines
    y -= 26
    pdf.line(45, y, 215, y)
    pdf.line(260, y, 430, y)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(45, y - 11, f"Class Teacher Signature: {class_teacher_name}")
    pdf.drawString(260, y - 11, f"Principal Signature: {principal_name}")

    pdf.showPage()
    pdf.save()
    return response


def generate_all_results_pdf(title, subjects, students_data, show_cumulative=False):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="results_sheet.pdf"'

    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, title)

    y -= 25
    headers = ["Rank", "Student"] + [s.name for s in subjects] + ["Total", "Average"]
    if show_cumulative:
        headers += ["T1", "T2", "T3", "Pass/Fail"]

    col_widths = [35, 110] + [40 for _ in subjects] + [50, 50]
    if show_cumulative:
        col_widths += [35, 35, 35, 55]

    rows = []
    for row in students_data:
        values = [row.get("rank_display", ""), row["student"].full_name]
        for subject in subjects:
            subject_result = row["subjects"].get(subject.name, {})
            values.append(subject_result.get("score", ""))
        total_value = row.get("cumulative_total") if show_cumulative else row.get("total")
        average_value = row.get("cumulative_average") if show_cumulative else row.get("average")
        values += [total_value, average_value]
        if show_cumulative:
            term_totals = row.get("term_totals", {})
            values += [
                term_totals.get(1, ""),
                term_totals.get(2, ""),
                term_totals.get(3, ""),
                row.get("pass_fail", ""),
            ]
        rows.append(values)

    pdf.setFont("Helvetica", 8)
    _draw_table(pdf, 30, y, col_widths, headers, rows, row_height=14, page_size=landscape(A4))

    pdf.showPage()
    pdf.save()
    return response
