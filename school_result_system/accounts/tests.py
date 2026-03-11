from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.capabilities import (
    CAP_APPROVE_FINANCE,
    CAP_APPROVE_RESULTS,
    CAP_ENTER_RESULTS,
    CAP_RECORD_FINANCE,
    CAP_RELEASE_RESULTS,
    has_capability,
)
from accounts.models import User


@override_settings(CANONICAL_HOST="")
class StaffLoginRoutingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username="teacher1",
            password="pass12345",
            is_teacher=True,
        )
        self.proprietor = User.objects.create_user(
            username="prop2",
            password="pass12345",
            is_proprietor=True,
        )
        self.bursar = User.objects.create_user(
            username="bursar1",
            password="pass12345",
        )
        bursar_group, _ = Group.objects.get_or_create(name="Bursar")
        self.bursar.groups.add(bursar_group)

    def test_teacher_login_redirects_to_teacher_dashboard(self):
        response = self.client.post(
            reverse("accounts:teacher_login"),
            {"username": "teacher1", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("accounts:teacher_dashboard"), fetch_redirect_response=False)

    def test_proprietor_login_redirects_to_proprietor_dashboard(self):
        response = self.client.post(
            reverse("accounts:teacher_login"),
            {"username": "prop2", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("accounts:proprietor_dashboard"), fetch_redirect_response=False)

    def test_bursar_login_redirects_to_billing_dashboard(self):
        response = self.client.post(
            reverse("accounts:teacher_login"),
            {"username": "bursar1", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("billing:dashboard"), fetch_redirect_response=False)


@override_settings(CANONICAL_HOST="")
class CapabilityMatrixTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_cap",
            password="pass12345",
            is_teacher=True,
        )
        self.proprietor = User.objects.create_user(
            username="prop_cap",
            password="pass12345",
            is_proprietor=True,
        )
        self.bursar = User.objects.create_user(
            username="bursar_cap",
            password="pass12345",
        )
        self.principal = User.objects.create_user(
            username="principal_cap",
            password="pass12345",
        )
        bursar_group, _ = Group.objects.get_or_create(name="Bursar")
        principal_group, _ = Group.objects.get_or_create(name="Principal")
        self.bursar.groups.add(bursar_group)
        self.principal.groups.add(principal_group)

    def test_teacher_capabilities(self):
        self.assertTrue(has_capability(self.teacher, CAP_ENTER_RESULTS))
        self.assertFalse(has_capability(self.teacher, CAP_RECORD_FINANCE))
        self.assertFalse(has_capability(self.teacher, CAP_APPROVE_RESULTS))

    def test_bursar_capabilities(self):
        self.assertTrue(has_capability(self.bursar, CAP_RECORD_FINANCE))
        self.assertFalse(has_capability(self.bursar, CAP_APPROVE_FINANCE))

    def test_principal_capabilities(self):
        self.assertTrue(has_capability(self.principal, CAP_APPROVE_FINANCE))
        self.assertFalse(has_capability(self.principal, CAP_RELEASE_RESULTS))

    def test_proprietor_capabilities(self):
        self.assertTrue(has_capability(self.proprietor, CAP_APPROVE_RESULTS))
        self.assertTrue(has_capability(self.proprietor, CAP_RELEASE_RESULTS))
