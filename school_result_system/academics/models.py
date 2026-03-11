from django.db import models

class AcademicSession(models.Model):
    name = models.CharField(max_length=20)  # e.g 2023/2024
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    name = models.CharField(max_length=50)  # JSS1, SS2, etc

    def __str__(self):
        return self.name


class Term(models.Model):
    TERM_CHOICES = (
        (1, "First Term"),
        (2, "Second Term"),
        (3, "Third Term"),
    )

    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    order = models.PositiveSmallIntegerField(choices=TERM_CHOICES)
    name = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ("session", "order")
        ordering = ("session", "order")

    def __str__(self):
        display_name = self.name or dict(self.TERM_CHOICES).get(self.order, "Term")
        return f"{self.session} - {display_name}"


class Subject(models.Model):
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name
