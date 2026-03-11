from django.conf import settings
from django.http import HttpResponse
from .services import grade_key_text, get_grade_policy

PRIMARY_TEXT = "#111827"
MUTED_TEXT = "#4b5563"
ROW_ALT = "#f3f4f6"
BORDER = "#9ca3af"
FONT_H1 = 12.5
FONT_H2 = 10
FONT_META = 8
FONT_CELL = 7.5
FONT_CELL_BOLD = 7.5
PDF_MARGIN = 24
LINE_STD = 0.55
LINE_STRONG = 0.8
ROW_HEIGHT_RESULT = 12
ROW_HEIGHT_BROADSHEET = 11


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


def _draw_signature_image(pdf, signature_file, x, y, width=90, height=26):
    from reportlab.lib.utils import ImageReader

    if not signature_file:
        return
    try:
        image = ImageReader(signature_file.path)
        pdf.drawImage(image, x, y, width=width, height=height, mask="auto")
    except Exception:
        return


def _draw_table(pdf, x, y, col_widths, headers, rows, row_height=16, page_size=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4

    if page_size is None:
        page_size = A4

    pdf.setStrokeColor(colors.HexColor(BORDER))
    pdf.setLineWidth(LINE_STD)
    total_width = sum(col_widths)

    def _fit_text(value, col_width, min_chars=2):
        text = str(value)
        # Approximate printable chars for Helvetica at small table sizes.
        max_chars = max(min_chars, int((col_width - 6) / 3.7))
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return f"{text[:max_chars-3]}..."

    pdf.setFillColor(colors.HexColor(PRIMARY_TEXT))
    pdf.rect(x, y - row_height + 2, total_width, row_height, fill=1, stroke=0)
    pdf.setFillColor(colors.white)

    cursor_x = x + 4
    for width, header in zip(col_widths, headers):
        header_text = _fit_text(header, width)
        header_font = 7 if width < 28 else 8
        pdf.setFont("Helvetica-Bold", header_font)
        pdf.drawString(cursor_x, y - row_height + 7, header_text)
        cursor_x += width

    current_y = y - row_height
    pdf.setFillColor(colors.black)
    for index, row in enumerate(rows):
        current_y -= row_height
        if index % 2 == 0:
            pdf.setFillColor(colors.HexColor(ROW_ALT))
            pdf.rect(x, current_y, total_width, row_height, fill=1, stroke=0)
            pdf.setFillColor(colors.black)

        cursor_x = x + 4
        for width, cell in zip(col_widths, row):
            text = _fit_text(cell, width)
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


def _domain_rating(score):
    if score >= 5:
        return "Excellent"
    if score == 4:
        return "Very Good"
    if score == 3:
        return "Good"
    if score == 2:
        return "Fair"
    return "Needs Support"


def _domain_matrix_rows(items):
    rows = []
    for label, score in items:
        rows.append(
            [
                label,
                "X" if score == 5 else "",
                "X" if score == 4 else "",
                "X" if score == 3 else "",
                "X" if score == 2 else "",
                "X" if score == 1 else "",
            ]
        )
    return rows


def _subject_header_map(subjects, max_len=12):
    used = set()
    mapping = {}
    common = {
        "english language": "English",
        "mathematics": "Math",
        "basic science": "Basic Sci",
        "basic technology": "Basic Tech",
        "social studies": "Social Std",
        "agricultural science": "Agric Sci",
        "computer studies": "Computer",
        "computer science": "Computer",
        "civic education": "Civic Edu",
        "technical drawing": "Tech Draw",
        "creative arts": "Creative Art",
        "physical and health education": "PHE",
    }
    for subject in subjects:
        name = str(getattr(subject, "name", "") or "").strip()
        preferred = str(getattr(subject, "short_name", "") or "").strip()
        base = preferred or common.get(name.lower(), name)
        if len(base) > max_len:
            base = base[:max_len]
        if not base:
            base = f"S{getattr(subject, 'id', '')}"
        candidate = base
        idx = 2
        while candidate in used:
            suffix = str(idx)
            candidate = f"{base[: max(1, max_len - len(suffix))]}{suffix}"
            idx += 1
        used.add(candidate)
        mapping[subject.name] = candidate
    return mapping


def _draw_subject_legend(pdf, x, y, entries, max_width):
    if not entries:
        return
    pdf.setFont("Helvetica", 6.8)
    line = "Subject keys: "
    approx_per_char = 3.4
    for short, full in entries:
        piece = f"{short}={full}; "
        if (len(line) + len(piece)) * approx_per_char > max_width:
            pdf.drawString(x, y, line[:220])
            y -= 9
            line = piece
            if y < 16:
                return
        else:
            line += piece
    if line.strip():
        pdf.drawString(x, y, line[:220])


def _grade_scale_rows():
    policy = get_grade_policy()
    return [
        ("A", f"{policy.grade_a_min}-100", "Excellent"),
        ("B", f"{policy.grade_b_min}-{policy.grade_a_min - 1}", "Very Good"),
        ("C", f"{policy.grade_c_min}-{policy.grade_b_min - 1}", "Good"),
        ("D", f"{policy.grade_d_min}-{policy.grade_c_min - 1}", "Fair"),
        ("F", f"0-{policy.grade_d_min - 1}", "Fail"),
    ]


def _draw_grade_scale_table(pdf, x, y_top, table_width=170):
    from reportlab.lib import colors

    row_h = 10
    headers = ["Grade", "Range", "Remark"]
    col_widths = [34, 50, table_width - 84]
    pdf.setFillColor(colors.HexColor(PRIMARY_TEXT))
    pdf.rect(x, y_top - row_h, table_width, row_h, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 7)
    cursor = x + 3
    for h, w in zip(headers, col_widths):
        pdf.drawString(cursor, y_top - row_h + 3, h)
        cursor += w
    pdf.setFillColor(colors.black)

    y = y_top - row_h
    for idx, row in enumerate(_grade_scale_rows()):
        y -= row_h
        if idx % 2 == 0:
            pdf.setFillColor(colors.HexColor(ROW_ALT))
            pdf.rect(x, y, table_width, row_h, fill=1, stroke=0)
            pdf.setFillColor(colors.black)
        cursor = x + 3
        for cell, w in zip(row, col_widths):
            pdf.setFont("Helvetica", 7)
            pdf.drawString(cursor, y + 3, str(cell))
            cursor += w
    return y


def _draw_wrapped_text_cell(pdf, x, y_baseline, text, max_width, line_height=8, max_lines=2):
    words = str(text or "").split()
    if not words:
        return 1
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if pdf.stringWidth(trial, "Helvetica", 7) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(words) > 1:
        tail = lines[-1]
        if not tail.endswith("..."):
            if len(tail) > 3:
                tail = tail[:-3] + "..."
            else:
                tail = "..."
            lines[-1] = tail
    for idx, line in enumerate(lines):
        pdf.drawString(x, y_baseline - (idx * line_height), line)
    return len(lines)


def generate_result_pdf(
    student, results, session, term, summary=None, position=None, domain_assessment=None
):
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
    principal_signature_file = None
    class_teacher_signature_file = None
    report_template_style = "classic"
    result_footer_note = ""
    print_density = "standard"
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        school_name = brand.school_name or school_name
        school_motto = brand.school_motto or school_motto
        principal_name = brand.principal_signature_name or principal_name
        class_teacher_name = brand.class_teacher_signature_name or class_teacher_name
        school_logo = brand.school_logo if brand.school_logo else None
        principal_signature_file = (
            brand.principal_signature_file if brand.principal_signature_file else None
        )
        class_teacher_signature_file = (
            brand.class_teacher_signature_file if brand.class_teacher_signature_file else None
        )
        report_template_style = brand.report_template_style or "classic"
        print_density = brand.report_print_density or "standard"
        result_footer_note = brand.result_footer_note or ""
    except Exception:
        pass

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = PDF_MARGIN
    content_width = width - (2 * margin)
    try:
        term_order = int(getattr(term, "order", 0) or 0)
    except (TypeError, ValueError):
        term_order = 0
    is_third_term = term_order == 3

    # Header
    y = height - 34
    _draw_school_badge(pdf, margin + 16, y + 2, school_logo=school_logo)
    pdf.setFont("Helvetica-Bold", FONT_H1)
    pdf.drawString(margin + 42, y + 6, school_name)
    pdf.setFont("Helvetica", FONT_META)
    pdf.setFillColor(colors.HexColor(MUTED_TEXT))
    pdf.drawString(margin + 42, y - 7, school_motto)
    pdf.setFillColor(colors.black)
    pdf.setStrokeColor(colors.HexColor(PRIMARY_TEXT))
    pdf.setLineWidth(LINE_STRONG)
    pdf.line(margin, y - 16, width - margin, y - 16)

    # Meta
    y -= 28
    pdf.setFont("Helvetica-Bold", FONT_H2)
    pdf.drawCentredString(width / 2, y, "STUDENT PERFORMANCE REPORT")
    y -= 14
    pdf.setFont("Helvetica", FONT_META)
    pdf.drawString(margin, y, f"Name: {student.full_name}")
    pdf.drawString(margin + 240, y, f"Admission No: {student.admission_number}")
    y -= 11
    pdf.drawString(margin, y, f"Class: {student.class_name or '-'}")
    pdf.drawString(margin + 240, y, f"Session: {session}")
    y -= 11
    pdf.drawString(margin, y, f"Term: {term}")
    pdf.drawString(
        margin + 240,
        y,
        f"Position: {summary.get('position', '') if summary else (position or '')}",
    )

    # Grade scale table (separate, top-right like standard secondary sheets)
    grade_table_y = _draw_grade_scale_table(
        pdf,
        x=width - margin - 170,
        y_top=height - 84,
        table_width=170,
    )

    # Subject table
    y = min(y - 16, grade_table_y - 10)
    headers = ["Subject", "CA1", "CA2", "Exam", "Total", "Grade"]
    col_widths = [content_width - 230, 36, 36, 46, 46, 36]
    rows = [
        [
            str(result.subject),
            result.ca1,
            result.ca2,
            result.exam,
            result.total_score,
            result.grade(),
        ]
        for result in results
    ]
    subject_count = len(rows)
    if subject_count == 0:
        rows = [["No result records", "", "", "", "", ""]]
        subject_count = 1

    table_top = y
    is_dense = print_density == "dense"
    row_height = 9 if is_dense else (10 if report_template_style == "compact" else ROW_HEIGHT_RESULT)
    table_height = row_height * (subject_count + 1)
    min_bottom_for_sections = 246
    available_for_table = max((table_top - min_bottom_for_sections), row_height * 4)
    if table_height > available_for_table:
        row_height = max(9, int(available_for_table / (subject_count + 1)))
        table_height = row_height * (subject_count + 1)

    # Header row
    x = margin
    pdf.setFillColor(colors.HexColor(PRIMARY_TEXT))
    pdf.rect(margin, table_top - row_height, content_width, row_height, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", FONT_CELL_BOLD)
    for w, h in zip(col_widths, headers):
        pdf.drawString(x + 3, table_top - row_height + 3, str(h))
        x += w
    pdf.setFillColor(colors.black)

    # Body rows
    pdf.setFont("Helvetica", FONT_CELL)
    current_y = table_top - row_height
    for i, row in enumerate(rows):
        current_y -= row_height
        if i % 2 == 0:
            pdf.setFillColor(colors.HexColor(ROW_ALT))
            pdf.rect(margin, current_y, content_width, row_height, stroke=0, fill=1)
            pdf.setFillColor(colors.black)
        x = margin
        for w, cell in zip(col_widths, row):
            text = str(cell)
            if len(text) > 34:
                text = f"{text[:31]}..."
            pdf.drawString(x + 3, current_y + 3, text)
            x += w
    y = current_y - 8

    term_total = sum(result.total_score for result in results)
    true_subject_count = len(results)
    term_average = round(term_total / true_subject_count, 2) if true_subject_count else 0
    pdf.setFont("Helvetica-Bold", FONT_META)
    pdf.drawString(margin, y, f"Term Total: {term_total}")
    pdf.drawString(margin + 130, y, f"Average: {term_average}")
    pdf.drawString(
        margin + 245,
        y,
        f"Position: {summary.get('position', '') if summary else (position or '')}",
    )
    y -= 11

    # Third-term cumulative summary
    if is_third_term and summary:
        pdf.setFont("Helvetica-Bold", FONT_META)
        pdf.drawString(margin, y, "Cumulative (Promotion Basis)")
        y -= 10
        pdf.setFont("Helvetica", FONT_CELL)
        pdf.drawString(margin, y, f"T1: {summary.get('term1_total', 0)}")
        pdf.drawString(margin + 70, y, f"T2: {summary.get('term2_total', 0)}")
        pdf.drawString(margin + 140, y, f"T3: {summary.get('term3_total', 0)}")
        pdf.drawString(margin + 210, y, f"Cum Total: {summary.get('cumulative_total', 0)}")
        pdf.drawString(margin + 315, y, f"Cum Avg: {summary.get('cumulative_average', 0)}")
        y -= 10
        pdf.drawString(margin, y, f"Attendance: {summary.get('attendance_rate', 0)}%")
        pdf.drawString(margin + 120, y, f"Behavior: {summary.get('behavior_average', 0)}")
        pdf.drawString(margin + 230, y, f"Decision: {summary.get('promotion_status', '')}")
        y -= 10
        reason = str(summary.get("promotion_reason", ""))[:88]
        pdf.drawString(margin, y, f"Basis: {reason}")
        y -= 10

    # Domain tables:
    # - First/Second term: show only current term values.
    # - Third term: show T1/T2/T3 values for full-session view.
    try:
        from academics.models import Term as AcademicTerm
        from .models import StudentDomainAssessment

        current_order = term_order
        if is_third_term:
            session_terms = list(AcademicTerm.objects.filter(session=session).order_by("order"))
            term_orders = [t.order for t in session_terms if t.order in (1, 2, 3)] or [1, 2, 3]
        else:
            if current_order in (1, 2, 3):
                term_orders = [current_order]
            else:
                term_orders = [1]
        assessments = {
            row.term.order: row
            for row in StudentDomainAssessment.objects.filter(
                student=student, session=session, term__order__in=term_orders
            ).select_related("term")
        }
    except Exception:
        term_orders = [1, 2, 3] if is_third_term else [getattr(term, "order", 1) or 1]
        assessments = {}

    def _v(order, attr):
        item = assessments.get(order)
        return getattr(item, attr) if item else "-"

    def _avg_for(attr):
        values = []
        for order in term_orders:
            value = _v(order, attr)
            if isinstance(value, (int, float)):
                values.append(float(value))
        if not values:
            return "-"
        return round(sum(values) / len(values), 2)

    if is_third_term:
        domain_headers = ["Key"] + [f"T{order}" for order in term_orders] + ["Avg"]
        key_col = 126
        metric_count = len(term_orders) + 1
        metric_col = int((content_width - key_col) / max(1, metric_count))
        domain_col_widths = [key_col] + [metric_col for _ in range(metric_count)]

        affective_rows = [
            ["Discipline"] + [_v(o, "discipline") for o in term_orders] + [_avg_for("discipline")],
            ["Respect"] + [_v(o, "respect") for o in term_orders] + [_avg_for("respect")],
            ["Punctuality"] + [_v(o, "punctuality") for o in term_orders] + [_avg_for("punctuality")],
            ["Teamwork"] + [_v(o, "teamwork") for o in term_orders] + [_avg_for("teamwork")],
            ["Leadership"] + [_v(o, "leadership") for o in term_orders] + [_avg_for("leadership")],
            ["Moral Conduct"] + [_v(o, "moral_conduct") for o in term_orders] + [_avg_for("moral_conduct")],
        ]
        psychomotor_rows = [
            ["Handwriting"] + [_v(o, "handwriting") for o in term_orders] + [_avg_for("handwriting")],
            ["Sport"] + [_v(o, "sport") for o in term_orders] + [_avg_for("sport")],
            ["Lab Practical"] + [_v(o, "laboratory_practical") for o in term_orders] + [_avg_for("laboratory_practical")],
            ["Tech Drawing"] + [_v(o, "technical_drawing") for o in term_orders] + [_avg_for("technical_drawing")],
            ["Creative Arts"] + [_v(o, "creative_arts") for o in term_orders] + [_avg_for("creative_arts")],
            ["Computer Prac"] + [_v(o, "computer_practical") for o in term_orders] + [_avg_for("computer_practical")],
        ]

        pdf.setFont("Helvetica-Bold", FONT_META)
        pdf.drawString(margin, y, "Affective Domain (1-5 scale, session view)")
        y -= 4
        y = _draw_table(
            pdf,
            margin,
            y,
            domain_col_widths,
            domain_headers,
            affective_rows,
            row_height=8,
            page_size=A4,
        ) - 6

        pdf.setFont("Helvetica-Bold", FONT_META)
        pdf.drawString(margin, y, "Psychomotor Domain (1-5 scale, session view)")
        y -= 4
        y = _draw_table(
            pdf,
            margin,
            y,
            domain_col_widths,
            domain_headers,
            psychomotor_rows,
            row_height=8,
            page_size=A4,
        ) - 7
    else:
        domain_headers = ["Key", "Value"]
        left_w = (content_width / 2) - 6
        right_x = margin + left_w + 12
        key_col = 82
        value_col = int(left_w - key_col)
        domain_col_widths = [key_col, value_col]
        order = term_orders[0]

        affective_rows = [
            ["Discipline", _v(order, "discipline")],
            ["Respect", _v(order, "respect")],
            ["Punctuality", _v(order, "punctuality")],
            ["Teamwork", _v(order, "teamwork")],
            ["Leadership", _v(order, "leadership")],
            ["Moral Conduct", _v(order, "moral_conduct")],
        ]
        psychomotor_rows = [
            ["Handwriting", _v(order, "handwriting")],
            ["Sport", _v(order, "sport")],
            ["Lab Practical", _v(order, "laboratory_practical")],
            ["Tech Drawing", _v(order, "technical_drawing")],
            ["Creative Arts", _v(order, "creative_arts")],
            ["Computer Prac", _v(order, "computer_practical")],
        ]

        pdf.setFont("Helvetica-Bold", FONT_META)
        pdf.drawString(margin, y, "Affective Domain (1-5 scale)")
        pdf.drawString(right_x, y, "Psychomotor Domain (1-5 scale)")
        y -= 4
        left_bottom = _draw_table(
            pdf,
            margin,
            y,
            domain_col_widths,
            domain_headers,
            affective_rows,
            row_height=9,
            page_size=A4,
        )
        right_bottom = _draw_table(
            pdf,
            right_x,
            y,
            domain_col_widths,
            domain_headers,
            psychomotor_rows,
            row_height=9,
            page_size=A4,
        )
        y = min(left_bottom, right_bottom) - 7

    # Attendance and remarks
    attendance_headers = ["Key"] + ([f"T{order}" for order in term_orders] if is_third_term else ["Value"])
    attendance_rows = [
        ["Times Opened"] + [_v(o, "times_school_opened") for o in term_orders],
        ["Times Present"] + [_v(o, "times_present") for o in term_orders],
        ["Times Absent"] + [_v(o, "times_absent") for o in term_orders],
        ["Teacher Remark"] + [str(_v(o, "teacher_remark")) for o in term_orders],
        ["Principal Remark"] + [str(_v(o, "principal_remark")) for o in term_orders],
    ]
    pdf.setFont("Helvetica-Bold", FONT_META)
    attendance_title = "Attendance / Remarks (Per Term)" if is_third_term else "Attendance / Remarks"
    pdf.drawString(margin, y, attendance_title)
    y -= 4

    from reportlab.lib import colors
    key_col = 120 if is_third_term else 110
    att_col_widths = [key_col] + [int((content_width - key_col) / max(1, len(term_orders))) for _ in term_orders]
    header_row_h = 9
    pdf.setFillColor(colors.HexColor(PRIMARY_TEXT))
    pdf.rect(margin, y - header_row_h, content_width, header_row_h, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 7)
    x = margin + 3
    for h, w in zip(attendance_headers, att_col_widths):
        pdf.drawString(x, y - header_row_h + 3, str(h))
        x += w
    pdf.setFillColor(colors.black)

    current_y = y - header_row_h
    for idx, row in enumerate(attendance_rows):
        is_remark = row[0] in {"Teacher Remark", "Principal Remark"}
        if is_remark:
            if is_third_term:
                row_h = 24
                wrap_max_lines = 3
                wrap_line_height = 6
                remark_font = 6.5
            else:
                row_h = 18
                wrap_max_lines = 2
                wrap_line_height = 7
                remark_font = 7
        else:
            row_h = 9
        current_y -= row_h
        if idx % 2 == 0:
            pdf.setFillColor(colors.HexColor(ROW_ALT))
            pdf.rect(margin, current_y, content_width, row_h, fill=1, stroke=0)
            pdf.setFillColor(colors.black)
        x = margin + 3
        for col_index, (cell, w) in enumerate(zip(row, att_col_widths)):
            if is_remark and col_index > 0:
                pdf.setFont("Helvetica", remark_font)
                _draw_wrapped_text_cell(
                    pdf,
                    x,
                    current_y + row_h - 6,
                    str(cell),
                    max_width=w - 6,
                    line_height=wrap_line_height,
                    max_lines=wrap_max_lines,
                )
            else:
                pdf.setFont("Helvetica", 7)
                text = str(cell)
                if len(text) > 25:
                    text = text[:22] + "..."
                pdf.drawString(x, current_y + 3, text)
            x += w
    y = current_y - 6

    # Footer
    pass_fail = summary.get("pass_fail", "") if summary else ""
    promotion_status = summary.get("promotion_status", "") if summary else ""
    if is_third_term and promotion_status:
        remark = promotion_status
    else:
        remark = "Promoted" if (is_third_term and pass_fail == "PASS") else "Not Promoted"
    if not is_third_term:
        remark = "Academic performance recorded."

    pdf.setFont("Helvetica", FONT_CELL)
    pdf.drawString(margin, y, f"Remark: {remark}")
    pdf.drawString(margin + 210, y, f"Grading Key: {_grade_key()}")
    y -= 17
    _draw_signature_image(pdf, class_teacher_signature_file, margin + 8, y + 5, width=80, height=24)
    _draw_signature_image(pdf, principal_signature_file, margin + 230, y + 5, width=80, height=24)
    pdf.setLineWidth(LINE_STD)
    pdf.line(margin, y, margin + 170, y)
    pdf.line(margin + 220, y, margin + 390, y)
    pdf.setFont("Helvetica", FONT_CELL)
    pdf.drawString(margin, y - 9, f"Class Teacher Signature: {class_teacher_name}")
    pdf.drawString(margin + 220, y - 9, f"Principal Signature: {principal_name}")
    pdf.drawRightString(width - margin, y - 9, "Generated by School Management Portal")
    if result_footer_note:
        pdf.drawString(margin, y - 19, f"Note: {result_footer_note[:110]}")

    pdf.showPage()
    pdf.save()
    return response


def generate_all_results_pdf(
    title, subjects, students_data, show_cumulative=False, density_override=None
):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="results_sheet.pdf"'

    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)
    print_density = "standard"
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        print_density = brand.report_print_density or "standard"
    except Exception:
        pass
    effective_density = density_override or print_density

    # Fit columns into page width and split subject columns into multiple parts if needed.
    available_width = width - 60  # 30 left + 30 right table margins
    fixed_width = 32 + 115 + 48 + 44  # rank + student + total + average
    if show_cumulative:
        fixed_width += 30 + 30 + 30 + 48 + 64  # t1,t2,t3,pass/fail,promotion
    min_subject_width = 32 if effective_density == "dense" else 40
    max_subject_cols = max(1, int((available_width - fixed_width) / min_subject_width))
    subject_list = list(subjects)
    if not subject_list:
        subject_chunks = [[]]
    else:
        subject_chunks = [
            subject_list[i : i + max_subject_cols]
            for i in range(0, len(subject_list), max_subject_cols)
        ]

    row_height = 12 if effective_density == "dense" else 14
    total_parts = len(subject_chunks)

    header_map = _subject_header_map(subject_list, max_len=12)

    for part_index, subject_chunk in enumerate(subject_chunks, start=1):
        y = height - 40
        pdf.setFont("Helvetica-Bold", 14)
        part_suffix = f" (Part {part_index}/{total_parts})" if total_parts > 1 else ""
        pdf.drawString(40, y, f"{title}{part_suffix}")

        y -= 25
        headers = ["Rank", "Student"] + [header_map.get(s.name, s.name) for s in subject_chunk] + ["Total", "Average"]
        if show_cumulative:
            headers += ["T1", "T2", "T3", "Pass/Fail", "Promotion"]

        subject_count = max(1, len(subject_chunk))
        subject_width = int((available_width - fixed_width) / subject_count)
        subject_width = max(20, min(52, subject_width))

        col_widths = [32, 115] + [subject_width for _ in subject_chunk] + [48, 44]
        if show_cumulative:
            col_widths += [30, 30, 30, 48, 64]
        total_width = sum(col_widths)
        if total_width > available_width:
            scale = available_width / total_width
            col_widths = [max(10, int(w * scale)) for w in col_widths]
            remainder = available_width - sum(col_widths)
            if remainder != 0:
                col_widths[-1] += remainder

        rows = []
        for row in students_data:
            values = [row.get("rank_display", ""), row["student"].full_name]
            for subject in subject_chunk:
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
                    row.get("promotion_status", ""),
                ]
            rows.append(values)

        pdf.setFont("Helvetica", 8)
        _draw_table(
            pdf,
            30,
            y,
            col_widths,
            headers,
            rows,
            row_height=row_height,
            page_size=landscape(A4),
        )

        pdf.setFont("Helvetica", FONT_CELL)
        legend_entries = [(header_map.get(s.name, s.name), s.name) for s in subject_chunk]
        _draw_subject_legend(pdf, 30, 30, legend_entries, max_width=width - 70)
        pdf.drawString(30, 22, f"Section {part_index} of {total_parts}")
        pdf.drawRightString(
            width - 30,
            22,
            f"Print: {'High Density' if effective_density == 'dense' else 'Standard'}",
        )
        pdf.showPage()

    pdf.save()
    return response


def generate_broadsheet_pdf(
    title, session, term, subjects, students_data, subject_averages, density_override=None
):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="broadsheet_{session}_{term}.pdf"'.replace(" ", "_")
    )

    school_name = getattr(settings, "SCHOOL_NAME", "Al-Waarith Model College")
    school_motto = getattr(settings, "SCHOOL_MOTTO", "Results and Records Portal")
    school_logo = None
    print_density = "standard"
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        school_name = brand.school_name or school_name
        school_motto = brand.school_motto or school_motto
        school_logo = brand.school_logo if brand.school_logo else None
        print_density = brand.report_print_density or "standard"
    except Exception:
        pass

    pdf = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = PDF_MARGIN
    content_width = width - (2 * margin)

    y = height - 28
    _draw_school_badge(pdf, margin + 14, y - 2, school_logo=school_logo)
    pdf.setFont("Helvetica-Bold", FONT_H1)
    pdf.drawString(margin + 36, y + 2, school_name)
    pdf.setFont("Helvetica", FONT_META)
    pdf.setFillColor(colors.HexColor(MUTED_TEXT))
    pdf.drawString(margin + 36, y - 10, school_motto)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", FONT_H2)
    pdf.drawRightString(width - margin, y + 2, title)
    pdf.setFont("Helvetica", FONT_META)
    pdf.drawRightString(width - margin, y - 10, f"Session: {session} | Term: {term}")
    pdf.setStrokeColor(colors.HexColor(PRIMARY_TEXT))
    pdf.line(margin, y - 16, width - margin, y - 16)

    y -= 28
    base_fixed = 32 + 120 + 48 + 44 + 36
    subject_space = max(content_width - base_fixed, 120)
    subject_col_width = max(26, int(subject_space / max(1, len(subjects))))
    col_widths = [32, 120] + [subject_col_width for _ in subjects] + [48, 44, 36]
    headers = ["#", "Student"] + [s.name for s in subjects] + ["Total", "Avg", "Pos"]

    rows = []
    for row in students_data:
        values = [row.get("rank", ""), row["student"].full_name]
        for subject in subjects:
            values.append(row["subjects"].get(subject.id, ""))
        values += [row.get("total", 0), row.get("average", 0), row.get("rank_display", "")]
        rows.append(values)

    avg_row = ["", "Class Avg"]
    for subject in subjects:
        avg_row.append(subject_averages.get(subject.id, ""))
    avg_row += ["", "", ""]
    rows.append(avg_row)

    effective_density = density_override or print_density
    row_height = 10 if effective_density == "dense" else ROW_HEIGHT_BROADSHEET
    _draw_table(
        pdf,
        margin,
        y,
        col_widths,
        headers,
        rows,
        row_height=row_height,
        page_size=landscape(A4),
    )

    footer_y = 28
    pdf.setStrokeColor(colors.HexColor(BORDER))
    pdf.setLineWidth(LINE_STD)
    pdf.line(margin, footer_y + 18, width - margin, footer_y + 18)
    pdf.setFont("Helvetica", FONT_CELL)
    pdf.drawString(margin, footer_y + 6, f"Generated by School Management Portal | {session} - {term}")
    pdf.drawRightString(
        width - margin,
        footer_y + 6,
        f"Official Broadsheet | Print: {'High Density' if effective_density == 'dense' else 'Standard'}",
    )

    pdf.showPage()
    pdf.save()
    return response
