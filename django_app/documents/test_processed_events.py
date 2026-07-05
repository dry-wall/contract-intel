"""
Tests for apply_processed_event -- the business logic consuming a
document-processed event and applying it to the matching Job. Plain
TestCase is fine here (not TransactionTestCase like Phase 2's upload view
tests) because there's no transaction.on_commit involved -- this function
makes direct ORM calls with no surrounding atomic block.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Organization
from .models import Document, Job
from .processed_events import apply_processed_event

User = get_user_model()


class ApplyProcessedEventTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="tester", password="pw", organization=self.org)
        self.document = Document.objects.create(
            owner=self.user, organization=self.org, original_filename="test.pdf",
            doc_type=Document.DocType.MSA, gcs_path="raw/org1/test.pdf",
        )
        self.job = Job.objects.create(document=self.document, status=Job.Status.PUBLISHED)

    def test_processing_event_marks_job_processing(self):
        apply_processed_event({"job_id": self.job.id, "status": "PROCESSING"})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.PROCESSING)

    def test_complete_event_marks_job_complete_with_result(self):
        result = {"clauses": [{"clause_type": "Governing Law"}], "risk_scores": [], "explanations": []}
        apply_processed_event({"job_id": self.job.id, "status": "COMPLETE", "result": result})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.COMPLETE)
        self.assertEqual(self.job.result, result)
        self.assertEqual(self.job.error_detail, "")

    def test_failed_event_marks_job_failed_with_error_detail(self):
        apply_processed_event(
            {"job_id": self.job.id, "status": "FAILED", "error_detail": "Vertex AI timeout"}
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.FAILED)
        self.assertEqual(self.job.error_detail, "Vertex AI timeout")

    def test_unknown_job_id_does_not_raise(self):
        # Must not crash the pull loop over a stale/malformed message.
        apply_processed_event({"job_id": 999999, "status": "COMPLETE", "result": {}})
        # No assertion needed beyond "this didn't raise" -- the real job is untouched.
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.PUBLISHED)

    def test_unknown_status_does_not_raise_or_change_job(self):
        apply_processed_event({"job_id": self.job.id, "status": "BOGUS_STATUS"})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.PUBLISHED)  # untouched

    def test_complete_event_with_missing_result_key_defaults_to_empty_dict(self):
        # Defensive: a malformed COMPLETE event without "result" shouldn't crash.
        apply_processed_event({"job_id": self.job.id, "status": "COMPLETE"})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.COMPLETE)
        self.assertEqual(self.job.result, {})
