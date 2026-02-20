from django.db.models import Sum, Count, F, IntegerField, ExpressionWrapper
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AcademicSession, Term
from students.models import Student
from results.models import Result
from .serializers import StudentSerializer, ResultSerializer
from .permissions import IsProprietorOrAdmin


def total_score_expression():
    return ExpressionWrapper(
        F("ca1") + F("ca2") + F("ca3") + F("project") + F("exam"),
        output_field=IntegerField(),
    )


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Student.objects.all().order_by("last_name", "first_name")
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated, IsProprietorOrAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ["last_name", "first_name", "class_name", "created_at"]
    search_fields = ["first_name", "last_name", "admission_number", "class_name"]


class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Result.objects.select_related("student", "subject", "session", "term").all()
    serializer_class = ResultSerializer
    permission_classes = [IsAuthenticated, IsProprietorOrAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ["created_at"]
    search_fields = ["student__first_name", "student__last_name", "student__admission_number"]

    def get_queryset(self):
        qs = super().get_queryset()
        session_id = self.request.query_params.get("session")
        term_id = self.request.query_params.get("term")
        student_id = self.request.query_params.get("student")
        if session_id:
            qs = qs.filter(session_id=session_id)
        if term_id:
            qs = qs.filter(term_id=term_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsProprietorOrAdmin]
    def get(self, request):
        session = AcademicSession.objects.filter(is_active=True).first()
        term = Term.objects.filter(session=session, is_active=True).first() if session else None
        if request.query_params.get("session"):
            session = AcademicSession.objects.filter(id=request.query_params.get("session")).first()
            term = Term.objects.filter(session=session, is_active=True).first() if session else None
        if request.query_params.get("term"):
            term = Term.objects.filter(id=request.query_params.get("term"), session=session).first()

        if not (session and term):
            return Response({"detail": "Session and term required."}, status=400)

        class_filter = (request.query_params.get("class_name") or "").strip()
        class_qs = Student.objects.exclude(class_name__isnull=True).exclude(class_name="")
        if class_filter:
            class_qs = class_qs.filter(class_name=class_filter)

        class_counts = list(
            class_qs.values("class_name").annotate(total=Count("id")).order_by("class_name")
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
                    if average > 45:
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
                    if average > 45:
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

        return Response(
            {
                "session": {"id": session.id, "name": session.name},
                "term": {"id": term.id, "name": term.name},
                "rows": rows,
            }
        )
