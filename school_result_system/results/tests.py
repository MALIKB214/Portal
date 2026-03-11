from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from unittest.mock import patch
from django.http import HttpResponse

from academics.models import AcademicSession, SchoolClass, Subject, Term
from results.forms import ResultForm
from results.models import (
    Notification,
    ParentPortalAccount,
    Result,
    ResultRelease,
    ResultSnapshot,
    StudentDomainAssessment,
    ResultWorkflow,
)
from results.services import GradePolicy, compute_rankings
from results.utils import generate_result_pdf
from results.workflow_service import (
    approve_results as workflow_approve_results,
    release_results as workflow_release_results,
    reopen_results as workflow_reopen_results,
    submit_results_for_class as workflow_submit_results_for_class,
)
from students.models import Student


@override_settings(CANONICAL_HOST="")
class ResultWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()

        self.proprietor = self.user_model.objects.create_user(
            username="prop1",
            password="pass12345",
            is_proprietor=True,
        )
        self.session = AcademicSession.objects.create(name="2025/2026", is_active=True)
        self.term = Term.objects.create(
            session=self.session,
            order=1,
            name="First Term",
            is_active=True,
        )
        self.student = Student.objects.create(
            first_name="Amina",
            last_name="Yusuf",
            admission_number="SCH/2026/001",
            gender="F",
            class_name="JSS2",
        )
        self.subject = Subject.objects.create(name="Mathematics")
        self.result = Result.objects.create(
            student=self.student,
            subject=self.subject,
            session=self.session,
            term=self.term,
            ca1=16,
            ca2=17,
            exam=50,
            status=Result.STATUS_SUBMITTED,
        )

    def test_check_result_blocked_until_release(self):
        response = self.client.post(
            reverse("results:check_result"),
            {
                "admission_number": self.student.admission_number,
                "session": self.session.id,
                "term": self.term.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Result not found for the selected session/term.")

    def test_release_flow_requires_approval_then_creates_release_and_notification(self):
        self.client.force_login(self.proprietor)

        approve_response = self.client.post(
            reverse("results:release_results"),
            {
                "action": "approve",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "jss2",
            },
            follow=True,
        )
        self.assertEqual(approve_response.status_code, 200)
        self.result.refresh_from_db()
        self.assertEqual(self.result.status, Result.STATUS_APPROVED)

        release_response = self.client.post(
            reverse("results:release_results"),
            {
                "action": "release",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "JSS2",
            },
            follow=True,
        )
        self.assertEqual(release_response.status_code, 200)
        self.assertTrue(
            ResultRelease.objects.filter(
                session=self.session,
                term=self.term,
                class_name="JSS2",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                student=self.student,
                session=self.session,
                term=self.term,
            ).exists()
        )

    def test_release_is_blocked_when_snapshot_missing_even_if_status_approved(self):
        self.client.force_login(self.proprietor)

        self.client.post(
            reverse("results:release_results"),
            {
                "action": "approve",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "JSS2",
            },
            follow=True,
        )
        ResultSnapshot.objects.filter(
            session=self.session,
            term=self.term,
            school_class__name__iexact="JSS2",
        ).delete()

        release_response = self.client.post(
            reverse("results:release_results"),
            {
                "action": "release",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "JSS2",
            },
            follow=True,
        )
        self.assertEqual(release_response.status_code, 200)
        self.assertContains(release_response, "Missing approval snapshots for")
        self.assertFalse(
            ResultRelease.objects.filter(
                session=self.session,
                term=self.term,
                class_name="JSS2",
            ).exists()
        )

    def test_release_is_blocked_when_snapshot_is_invalid(self):
        self.client.force_login(self.proprietor)

        self.client.post(
            reverse("results:release_results"),
            {
                "action": "approve",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "JSS2",
            },
            follow=True,
        )
        snapshot = ResultSnapshot.objects.filter(
            session=self.session,
            term=self.term,
            school_class__name__iexact="JSS2",
        ).first()
        self.assertIsNotNone(snapshot)
        snapshot.signature = "tampered-signature"
        snapshot.save(update_fields=["signature", "updated_at"])

        release_response = self.client.post(
            reverse("results:release_results"),
            {
                "action": "release",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": "JSS2",
            },
            follow=True,
        )
        self.assertEqual(release_response.status_code, 200)
        self.assertContains(release_response, "Invalid approval snapshots for")
        self.assertFalse(
            ResultRelease.objects.filter(
                session=self.session,
                term=self.term,
                class_name="JSS2",
            ).exists()
        )

    def test_download_result_pdf_forbidden_before_release(self):
        response = self.client.get(
            reverse(
                "results:download_result",
                args=[self.student.id, self.session.id, self.term.id],
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_release_requires_approved_scores(self):
        with self.assertRaises(ValueError):
            workflow_release_results(self.session, self.term, self.proprietor, school_class=None)

    def test_approve_without_submitted_results_keeps_workflow_draft(self):
        school_class = SchoolClass.objects.create(name="JSS2")
        self.result.status = Result.STATUS_DRAFT
        self.result.save(update_fields=["status"])

        updated = workflow_approve_results(
            self.session, self.term, self.proprietor, school_class=school_class
        )
        self.assertEqual(updated, 0)

        workflow = ResultWorkflow.objects.get(
            session=self.session, term=self.term, school_class=school_class
        )
        self.assertEqual(workflow.status, ResultWorkflow.STATUS_DRAFT)

    def test_reopen_class_fails_if_term_released_globally(self):
        school_class = SchoolClass.objects.create(name="JSS2")
        ResultRelease.objects.create(
            session=self.session,
            term=self.term,
            class_name="",
            released_by=self.proprietor,
        )

        with self.assertRaises(ValueError):
            workflow_reopen_results(
                session=self.session,
                term=self.term,
                user=self.proprietor,
                school_class=school_class,
                reason="Correction",
            )

    def test_parent_account_login_works(self):
        parent_user = self.user_model.objects.create_user(
            username="parent_sch2026001",
            password="Parent@123",
            email="parent@example.com",
        )
        ParentPortalAccount.objects.create(user=parent_user, student=self.student, is_active=True)
        response = self.client.post(
            reverse("results:parent_login"),
            {"username": "parent_sch2026001", "password": "Parent@123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent Dashboard")

    def test_parent_dashboard_lists_only_released_terms(self):
        second_term = Term.objects.create(
            session=self.session,
            order=2,
            name="Second Term",
        )
        self.client.force_login(self.proprietor)
        self.client.post(
            reverse("results:release_results"),
            {
                "action": "approve",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": self.student.class_name,
            },
        )
        self.client.post(
            reverse("results:release_results"),
            {
                "action": "release",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": self.student.class_name,
            },
        )
        self.client.logout()

        session = self.client.session
        session["parent_student_id"] = self.student.id
        session.save()

        response = self.client.get(reverse("results:parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.term))
        self.assertNotContains(response, str(second_term))

    def test_check_form_lists_only_released_terms_for_student_and_session(self):
        second_term = Term.objects.create(
            session=self.session,
            order=2,
            name="Second Term",
        )
        self.client.force_login(self.proprietor)
        self.client.post(
            reverse("results:release_results"),
            {
                "action": "approve",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": self.student.class_name,
            },
        )
        self.client.post(
            reverse("results:release_results"),
            {
                "action": "release",
                "session": self.session.id,
                "term": self.term.id,
                "class_name": self.student.class_name,
            },
        )
        self.client.logout()

        response = self.client.get(
            reverse("results:check_result"),
            {
                "admission_number": self.student.admission_number,
                "session": self.session.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.term))
        self.assertNotContains(response, str(second_term))

    def test_release_page_shows_missing_snapshot_count(self):
        class_jss2 = SchoolClass.objects.create(name="JSS2")
        class_ss1 = SchoolClass.objects.create(name="SS1")
        self.student.school_class = class_jss2
        self.student.save(update_fields=["school_class"])
        self.result.status = Result.STATUS_SUBMITTED
        self.result.save(update_fields=["status"])

        student_two = Student.objects.create(
            first_name="Ife",
            last_name="Ayo",
            admission_number="SCH/2026/099",
            gender="F",
            class_name="SS1",
            school_class=class_ss1,
        )
        Result.objects.create(
            student=student_two,
            subject=self.subject,
            session=self.session,
            term=self.term,
            ca1=10,
            ca2=10,
            exam=25,
            status=Result.STATUS_DRAFT,
        )

        workflow_approve_results(
            self.session, self.term, self.proprietor, school_class=class_jss2
        )

        self.client.force_login(self.proprietor)
        response = self.client.get(
            reverse("results:release_results"),
            {"session": self.session.id, "term": self.term.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["snapshot_health"]["missing"], 1)
        self.assertContains(response, "Missing: 1")

    def test_submit_uses_case_insensitive_class_matching(self):
        school_class = SchoolClass.objects.create(name="JSS2")
        self.result.status = Result.STATUS_DRAFT
        self.result.student.school_class = None
        self.result.student.class_name = "jss2"
        self.result.student.save(update_fields=["school_class", "class_name"])
        self.result.save(update_fields=["status"])

        updated = workflow_submit_results_for_class(
            self.session, self.term, school_class, self.proprietor
        )
        self.assertEqual(updated, 1)
        self.result.refresh_from_db()
        self.assertEqual(self.result.status, Result.STATUS_SUBMITTED)


@override_settings(CANONICAL_HOST="")
class ResultFormValidationTests(TestCase):
    def setUp(self):
        self.session_1 = AcademicSession.objects.create(name="2025/2026")
        self.session_2 = AcademicSession.objects.create(name="2026/2027")
        self.term_session_2 = Term.objects.create(
            session=self.session_2,
            order=1,
            name="First Term",
        )
        self.student = Student.objects.create(
            first_name="Musa",
            last_name="Bello",
            admission_number="SCH/2026/002",
            gender="M",
            class_name="SS1",
        )
        self.subject = Subject.objects.create(name="Biology")

    def test_term_must_match_selected_session(self):
        form = ResultForm(
            data={
                "student": self.student.id,
                "subject": self.subject.id,
                "session": self.session_1.id,
                "term": self.term_session_2.id,
                "ca1": 10,
                "ca2": 10,
                "exam": 30,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Select a valid choice. That choice is not one of the available choices.",
            form.errors["term"],
        )

    def test_model_clean_rejects_session_term_mismatch(self):
        result = Result(
            student=self.student,
            subject=self.subject,
            session=self.session_1,
            term=self.term_session_2,
            ca1=10,
            ca2=10,
            exam=20,
        )
        with self.assertRaises(ValidationError):
            result.full_clean()


@override_settings(CANONICAL_HOST="")
class DownloadAllResultsPdfScopeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.teacher_class = SchoolClass.objects.create(name="JSS2")
        self.teacher = self.user_model.objects.create_user(
            username="teacher_scope",
            password="pass12345",
            is_teacher=True,
            teacher_class=self.teacher_class,
        )
        self.proprietor = self.user_model.objects.create_user(
            username="prop_scope",
            password="pass12345",
            is_proprietor=True,
        )
        self.session = AcademicSession.objects.create(name="2025/2026", is_active=True)
        self.term = Term.objects.create(
            session=self.session,
            order=1,
            name="First Term",
            is_active=True,
        )
        self.subject = Subject.objects.create(name="English")
        self.student_teacher_class = Student.objects.create(
            first_name="Class",
            last_name="Student",
            admission_number="SCH/2026/301",
            gender="M",
            class_name="JSS2",
        )
        self.student_other_class = Student.objects.create(
            first_name="Other",
            last_name="Student",
            admission_number="SCH/2026/302",
            gender="F",
            class_name="SS1",
        )
        Result.objects.create(
            student=self.student_teacher_class,
            subject=self.subject,
            session=self.session,
            term=self.term,
            ca1=15,
            ca2=15,
            exam=40,
        )
        Result.objects.create(
            student=self.student_other_class,
            subject=self.subject,
            session=self.session,
            term=self.term,
            ca1=14,
            ca2=14,
            exam=42,
        )

    @patch("results.views.generate_all_results_pdf")
    def test_teacher_download_all_results_is_scoped_to_teacher_class(self, mock_pdf):
        mock_pdf.return_value = HttpResponse("ok")
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("results:download_all_results"))
        self.assertEqual(response.status_code, 200)

        students_data = mock_pdf.call_args[0][2]
        student_names = [row["student"].full_name for row in students_data]
        self.assertIn(self.student_teacher_class.full_name, student_names)
        self.assertNotIn(self.student_other_class.full_name, student_names)

    @patch("results.views.generate_all_results_pdf")
    def test_proprietor_download_all_results_includes_all_classes(self, mock_pdf):
        mock_pdf.return_value = HttpResponse("ok")
        self.client.force_login(self.proprietor)
        response = self.client.get(reverse("results:download_all_results"))
        self.assertEqual(response.status_code, 200)

        students_data = mock_pdf.call_args[0][2]
        student_names = [row["student"].full_name for row in students_data]
        self.assertIn(self.student_teacher_class.full_name, student_names)
        self.assertIn(self.student_other_class.full_name, student_names)


class ResultServicesTests(TestCase):
    def test_competition_ranking_policy(self):
        rows = [
            {"student_id": 1, "total": 500},
            {"student_id": 2, "total": 500},
            {"student_id": 3, "total": 450},
        ]
        ranked = compute_rankings(rows, total_key="total", ranking_policy="competition")
        ranks = [row["rank"] for row in ranked]
        displays = [row["rank_display"] for row in ranked]
        self.assertEqual(ranks, [1, 1, 3])
        self.assertEqual(displays, ["1st", "1st", "3rd"])

    def test_grade_policy_fail_rule_45_and_below(self):
        policy = GradePolicy(pass_mark=45)
        self.assertEqual(policy.pass_fail_for(45), "FAIL")
        self.assertEqual(policy.pass_fail_for(44.99), "FAIL")
        self.assertEqual(policy.pass_fail_for(45.1), "PASS")


@override_settings(CANONICAL_HOST="")
class ResultPdfTermRenderingTests(TestCase):
    class FakeCanvas:
        last_instance = None

        def __init__(self, *_args, **_kwargs):
            self.texts = []
            ResultPdfTermRenderingTests.FakeCanvas.last_instance = self

        def setFont(self, *_args, **_kwargs):
            return None

        def setFillColor(self, *_args, **_kwargs):
            return None

        def setStrokeColor(self, *_args, **_kwargs):
            return None

        def setLineWidth(self, *_args, **_kwargs):
            return None

        def line(self, *_args, **_kwargs):
            return None

        def rect(self, *_args, **_kwargs):
            return None

        def circle(self, *_args, **_kwargs):
            return None

        def drawImage(self, *_args, **_kwargs):
            return None

        def drawString(self, _x, _y, text):
            self.texts.append(str(text))

        def drawCentredString(self, _x, _y, text):
            self.texts.append(str(text))

        def drawRightString(self, _x, _y, text):
            self.texts.append(str(text))

        def showPage(self):
            return None

        def save(self):
            return None

        def stringWidth(self, text, *_args, **_kwargs):
            return float(len(str(text)) * 4)

    def setUp(self):
        self.session = AcademicSession.objects.create(name="2025/2026")
        self.term1 = Term.objects.create(session=self.session, order=1, name="First Term")
        self.term2 = Term.objects.create(session=self.session, order=2, name="Second Term")
        self.term3 = Term.objects.create(session=self.session, order=3, name="Third Term")
        self.subject = Subject.objects.create(name="Mathematics")
        self.student = Student.objects.create(
            first_name="Ayo",
            last_name="Bello",
            admission_number="SCH/2026/501",
            gender="M",
            class_name="JSS2",
        )
        self.results = []
        for term in (self.term1, self.term2, self.term3):
            self.results.append(
                Result.objects.create(
                    student=self.student,
                    subject=self.subject,
                    session=self.session,
                    term=term,
                    ca1=15,
                    ca2=16,
                    exam=45,
                )
            )
            StudentDomainAssessment.objects.create(
                student=self.student,
                session=self.session,
                term=term,
                discipline=4,
                respect=3,
                punctuality=5,
                teamwork=4,
                leadership=3,
                moral_conduct=4,
                handwriting=4,
                sport=3,
                laboratory_practical=4,
                technical_drawing=3,
                creative_arts=5,
                computer_practical=4,
                times_school_opened=60,
                times_present=55,
                times_absent=5,
                teacher_remark=f"Teacher remark T{term.order}",
                principal_remark=f"Principal remark T{term.order}",
            )

    @patch("reportlab.pdfgen.canvas.Canvas", new=FakeCanvas)
    def test_non_third_term_pdf_shows_key_value_only(self):
        term1_results = Result.objects.filter(
            student=self.student, session=self.session, term=self.term1
        ).select_related("subject")
        generate_result_pdf(self.student, term1_results, self.session, self.term1, summary=None)
        texts = self.FakeCanvas.last_instance.texts

        self.assertIn("Value", texts)
        self.assertIn("Attendance / Remarks", texts)
        self.assertNotIn("Attendance / Remarks (Per Term)", texts)
        self.assertNotIn("T2", texts)
        self.assertNotIn("T3", texts)

    @patch("reportlab.pdfgen.canvas.Canvas", new=FakeCanvas)
    def test_third_term_pdf_shows_t1_t2_t3(self):
        term3_results = Result.objects.filter(
            student=self.student, session=self.session, term=self.term3
        ).select_related("subject")
        summary = {
            "term1_total": 76,
            "term2_total": 74,
            "term3_total": 76,
            "cumulative_total": 226,
            "cumulative_average": 75.33,
            "pass_fail": "PASS",
            "promotion_status": "PROMOTED",
            "promotion_reason": "Strong cumulative performance.",
        }
        generate_result_pdf(self.student, term3_results, self.session, self.term3, summary=summary)
        texts = self.FakeCanvas.last_instance.texts

        self.assertIn("T1", texts)
        self.assertIn("T2", texts)
        self.assertIn("T3", texts)
        self.assertIn("Avg", texts)
        self.assertIn("Attendance / Remarks (Per Term)", texts)
