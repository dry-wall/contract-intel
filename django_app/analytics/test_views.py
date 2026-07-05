from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from documents.models import Document, Job

User = get_user_model()


class JobBenchmarkViewTests(TestCase):
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
                    {"clause_type": "Limitation of Liability", "text": "...", "page": 1},
                    {"clause_type": "Governing Law", "text": "...", "page": 1},
                ],
                "risk_scores": [
                    {"clause_index": 0, "risk_score": 90, "risk_category": "HIGH"},
                ],
                "explanations": [],
            },
        )

    @patch("analytics.views.get_risk_category_distribution")
    @patch("analytics.views.get_risk_percentile")
    def test_benchmark_view_returns_percentile_for_scored_clauses_only(
        self, mock_percentile, mock_distribution
    ):
        mock_percentile.return_value = {"percentile": 82.5, "population_size": 40}
        mock_distribution.return_value = [{"risk_category": "HIGH", "count": 5}]

        response = self.client.get(reverse("analytics:job_benchmark", args=[self.job.id]))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Only ONE clause has a risk score (index 0); Governing Law (index 1)
        # has none in this fixture and must be skipped, not crash the view.
        self.assertEqual(len(body["clause_benchmarks"]), 1)
        self.assertEqual(body["clause_benchmarks"][0]["clause_type"], "Limitation of Liability")
        self.assertEqual(body["clause_benchmarks"][0]["percentile"], 82.5)

        # Distribution called once scoped to the org, once unscoped (platform-wide).
        self.assertEqual(mock_distribution.call_count, 2)
        call_kwargs = [c.kwargs for c in mock_distribution.call_args_list]
        self.assertIn({"organization_id": self.org.id}, call_kwargs)
        self.assertIn({"organization_id": None}, call_kwargs)

    def test_benchmark_view_rejects_incomplete_job(self):
        self.job.status = Job.Status.PROCESSING
        self.job.save()

        response = self.client.get(reverse("analytics:job_benchmark", args=[self.job.id]))
        self.assertEqual(response.status_code, 400)

    def test_benchmark_view_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("analytics:job_benchmark", args=[self.job.id]))
        self.assertEqual(response.status_code, 302)

    def test_benchmark_view_scopes_to_own_organization(self):
        other_org = Organization.objects.create(name="Other Org")
        other_user = User.objects.create_user(username="other", password="pw", organization=other_org)
        self.client.force_login(other_user)

        response = self.client.get(reverse("analytics:job_benchmark", args=[self.job.id]))
        self.assertEqual(response.status_code, 404)  # can't see another org's job
