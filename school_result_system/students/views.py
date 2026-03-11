from django.shortcuts import render, redirect, get_object_or_404
from accounts.permissions import teacher_required, teacher_with_class_required
from .models import Student
from .forms import StudentForm


@teacher_with_class_required
def student_list(request):
    if request.user.teacher_class:
        students = Student.objects.filter(
            school_class=request.user.teacher_class
        ).order_by("class_name", "last_name")
    else:
        students = Student.objects.none()
    return render(request, "students/student_list.html", {"students": students})


@teacher_with_class_required
def student_add(request):
    if request.method == "POST":
        form = StudentForm(request.POST, user=request.user)
        if form.is_valid():
            student = form.save(commit=False)
            if request.user.teacher_class:
                student.school_class = request.user.teacher_class
                student.class_name = request.user.teacher_class.name
            student.save()
            return redirect("students:list")
    else:
        form = StudentForm(user=request.user)

    return render(request, "students/student_form.html", {"form": form})


@teacher_with_class_required
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.user.teacher_class and student.school_class_id != request.user.teacher_class.id:
        return redirect("students:list")

    if request.method == "POST":
        form = StudentForm(request.POST, instance=student, user=request.user)
        if form.is_valid():
            student = form.save(commit=False)
            if request.user.teacher_class:
                student.school_class = request.user.teacher_class
                student.class_name = request.user.teacher_class.name
            student.save()
            return redirect("students:list")
    else:
        form = StudentForm(instance=student, user=request.user)

    return render(request, "students/student_form.html", {"form": form})
