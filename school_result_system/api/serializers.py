from rest_framework import serializers

from students.models import Student
from results.models import Result


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "last_name",
            "admission_number",
            "gender",
            "class_name",
            "created_at",
        ]


class ResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    total_score = serializers.IntegerField(read_only=True)
    grade = serializers.SerializerMethodField()

    class Meta:
        model = Result
        fields = [
            "id",
            "student",
            "student_name",
            "subject",
            "subject_name",
            "session",
            "session_name",
            "term",
            "term_name",
            "ca1",
            "ca2",
            "ca3",
            "project",
            "exam",
            "total_score",
            "grade",
            "created_at",
        ]

    def get_grade(self, obj):
        return obj.grade()
