"""
Phase 8 page tests. BigQuery calls (get_risk_percentile,
get_risk_category_distribution) are mocked here — same pattern as Phase 7's
analytics tests — since there's no live BigQuery in a test environment.
These verify template rendering, context correctness, and access control
for every new page, without needing real GCP credentials.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from .models import Document, Job

User = get_user_model()


class DocumentsListPageTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="tester", password="pw", organization=self.org)
        self.client.force_login(self.user)

    def test_empty_state_when_no_documents(self):
        response = self.client.get(reverse("documents:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No documents yet")

    def test_lists_only_own_organization_documents(self):
        other_org = Organization.objects.create(name="Other Org")
        other_user = User.objects.create_user(username="other", password="pw", organization=other_org)
        other_doc = Document.objects.create(
            owner=other_user, organization=other_org, original_filename="other_org_secret.pdf",
            doc_type=Document.DocType.NDA, gcs_path="raw/other/x.pdf",
        )
        Job.objects.create(document=other_doc, status=Job.Status.COMPLETE)

        my_doc = Document.objects.create(
            owner=self.user, organization=self.org, original_filename="my_contract.pdf",
            doc_type=Document.DocType.MSA, gcs_path="raw/mine/x.pdf",
        )
        Job.objects.create(document=my_doc, status=Job.Status.PROCESSING)

        response = self.client.get(reverse("documents:list"))
        self.assertContains(response, "my_contract.pdf")
        self.assertNotContains(response, "other_org_secret.pdf")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("documents:list"))
        self.assertEqual(response.status_code, 302)


class UploadPageTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="tester", password="pw", organization=self.org)
        self.client.force_login(self.user)

    def test_get_renders_real_upload_page(self):
        response = self.client.get(reverse("documents:upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dropzone")
        self.assertContains(response, "Analyze contract")

    def test_upload_button_disabled_without_organization(self):
        user_no_org = User.objects.create_user(username="noorg", password="pw")
        self.client.force_login(user_no_org)
        response = self.client.get(reverse("documents:upload"))
        self.assertContains(response, "no organization assigned")
        self.assertContains(response, "disabled")


class JobStatusPageTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="tester", password="pw", organization=self.org)
        self.client.force_login(self.user)
        self.document = Document.objects.create(
            owner=self.user, organization=self.org, original_filename="test.pdf",
            doc_type=Document.DocType.MSA, gcs_path="raw/org1/test.pdf",
        )
        self.job = Job.objects.create(document=self.document, status=Job.Status.PROCESSING)

    def test_status_page_renders_with_stepper(self):
        response = self.client.get(reverse("documents:status", args=[self.job.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stepper")
        self.assertContains(response, str(self.job.id))

    def test_status_json_returns_current_status(self):
        response = self.client.get(reverse("documents:status_json", args=[self.job.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "PROCESSING", "error_detail": ""})

    def test_status_json_includes_error_detail_when_failed(self):
        self.job.mark_failed("Vertex AI timeout")
        response = self.client.get(reverse("documents:status_json", args=[self.job.id]))
        self.assertEqual(response.json()["status"], "FAILED")
        self.assertEqual(response.json()["error_detail"], "Vertex AI timeout")

    def test_cannot_view_another_orgs_job_status(self):
        other_org = Organization.objects.create(name="Other Org")
        other_user = User.objects.create_user(username="other", password="pw", organization=other_org)
        self.client.force_login(other_user)
        response = self.client.get(reverse("documents:status_json", args=[self.job.id]))
        self.assertEqual(response.status_code, 404)


class JobResultsPageTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="tester", password="pw", organization=self.org)
        self.client.force_login(self.user)
        self.document = Document.objects.create(
            owner=self.user, organization=self.org, original_filename="test.pdf",
            doc_type=Document.DocType.MSA, gcs_path="raw/org1/test.pdf",
        )
        self.job = Job.objects.create(
            document=self.document,
            status=Job.Status.COMPLETE,
            result={
                "clauses": [
                    {"clause_type": "Limitation of Liability", "text": "Liability is uncapped.", "page": 1},
                    {"clause_type": "Governing Law", "text": "Delaware law applies.", "page": 1},
                ],
                "risk_scores": [
                    {"clause_index": 0, "risk_score": 92, "risk_category": "HIGH", "rationale": "Very risky."},
                ],
                "explanations": [
                    {"clause_index": 0, "explanation": "You could owe unlimited damages."},
                ],
            },
        )

    @patch("documents.views.get_risk_category_distribution")
    @patch("documents.views.get_risk_percentile")
    def test_results_page_renders_clauses_and_chart(self, mock_percentile, mock_distribution):
        mock_percentile.return_value = {"percentile": 88.0, "population_size": 25}
        mock_distribution.return_value = [{"risk_category": "HIGH", "count": 3}]

        response = self.client.get(reverse("documents:results", args=[self.job.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Limitation of Liability")
        self.assertContains(response, "badge-high")
        self.assertContains(response, "You could owe unlimited damages")
        self.assertContains(response, "riskChart")
        # Governing Law has no risk score in this fixture -> no badge for it,
        # but it should still be listed as a clause.
        self.assertContains(response, "Governing Law")

        # Percentile was only computed for the risk-scored clause.
        mock_percentile.assert_called_once()

    def test_results_page_404s_for_incomplete_job(self):
        self.job.status = Job.Status.PROCESSING
        self.job.save()
        response = self.client.get(reverse("documents:results", args=[self.job.id]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_view_another_orgs_results(self):
        other_org = Organization.objects.create(name="Other Org")
        other_user = User.objects.create_user(username="other", password="pw", organization=other_org)
        self.client.force_login(other_user)
        response = self.client.get(reverse("documents:results", args=[self.job.id]))
        self.assertEqual(response.status_code, 404)


class LoginPageTests(TestCase):
    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_login_with_correct_credentials_redirects(self):
        org = Organization.objects.create(name="Test Org")
        User.objects.create_user(username="tester", password="correctpw", organization=org)
        response = self.client.post(reverse("login"), {"username": "tester", "password": "correctpw"})
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_shows_error(self):
        org = Organization.objects.create(name="Test Org")
        User.objects.create_user(username="tester", password="correctpw", organization=org)
        response = self.client.post(reverse("login"), {"username": "tester", "password": "wrongpw"})
        self.assertEqual(response.status_code, 200)  # re-renders the form, no redirect
        self.assertContains(response, "Incorrect username or password")
