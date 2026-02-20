from django.contrib import admin
from .models import AcademicSession, SchoolClass, Subject, Term

admin.site.register(AcademicSession)
admin.site.register(SchoolClass)
admin.site.register(Subject)
admin.site.register(Term)

