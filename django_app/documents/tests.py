"""
Tests for the ingestion view. GCS and Pub/Sub are mocked — these tests verify
OUR wiring logic (form validation, transaction.on_commit ordering, state
transitions), not the real Google client libraries. Uses TransactionTestCase
instead of TestCase because transaction.on_commit callbacks never fire inside
Django's normal TestCase (it wraps each test in an outer atomic block that
rolls back rather than commits, so on_commit hooks are silently skipped).
"""
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import reverse

from .models import Document, Job

User = get_user_model()


def make_pdf_upload(name="contract.pdf", content=b"%PDF-1.4 fake pdf content"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type="application/pdf")


class UploadDocumentViewTests(TransactionTestCase):
    def setUp(self):
        from accounts.models import Organization

        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(
            username="tester", password="pw12345", organization=self.org
        )
        self.client.force_login(self.user)

    @patch("documents.views.publish_document_uploaded")
    @patch("documents.views.upload_pdf")
    def test_successful_upload_creates_document_job_and_publishes(self, mock_upload_pdf, mock_publish):
        mock_upload_pdf.return_value = "raw/org1/fake123.pdf"
        mock_publish.return_value = "mock-message-id-001"

        response = self.client.post(
            reverse("documents:upload"),
            data={"file": make_pdf_upload(), "doc_type": Document.DocType.NDA},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        document = Document.objects.get(pk=body["document_id"])
        job = Job.objects.get(pk=body["job_id"])

        self.assertEqual(document.gcs_path, "raw/org1/fake123.pdf")
        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.organization, self.org)
        self.assertEqual(document.doc_type, Document.DocType.NDA)

        # The on_commit publish must have already fired by the time the
        # response is built, and must have moved the job to PUBLISHED.
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.PUBLISHED)
        self.assertEqual(job.pubsub_message_id, "mock-message-id-001")
        self.assertEqual(body["status"], "PUBLISHED")

        mock_upload_pdf.assert_called_once()
        mock_publish.assert_called_once_with(job)

    @patch("documents.views.publish_document_uploaded")
    @patch("documents.views.upload_pdf")
    def test_publish_failure_marks_job_failed_not_stuck_pending(self, mock_upload_pdf, mock_publish):
        mock_upload_pdf.return_value = "raw/org1/fake456.pdf"
        mock_publish.side_effect = RuntimeError("pubsub unreachable")

        response = self.client.post(
            reverse("documents:upload"),
            data={"file": make_pdf_upload(), "doc_type": Document.DocType.MSA},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        job = Job.objects.get(pk=body["job_id"])
        job.refresh_from_db()

        # Document/Job still exist (created before the transaction committed)
        # but the job reflects the publish failure rather than being silently
        # stuck at PENDING forever.
        self.assertEqual(job.status, Job.Status.FAILED)
        self.assertIn("Pub/Sub", job.error_detail)

    def test_rejects_non_pdf_content_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        text_file = SimpleUploadedFile("not_a_pdf.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            reverse("documents:upload"), data={"file": text_file, "doc_type": Document.DocType.OTHER}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_rejects_oversized_file(self):
        from django.test import override_settings

        with override_settings(MAX_UPLOAD_BYTES=10):
            response = self.client.post(
                reverse("documents:upload"),
                data={"file": make_pdf_upload(content=b"x" * 100), "doc_type": Document.DocType.OTHER},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_rejects_upload_with_no_organization(self):
        user_no_org = User.objects.create_user(username="noorg", password="pw12345")
        self.client.force_login(user_no_org)
        response = self.client.post(
            reverse("documents:upload"),
            data={"file": make_pdf_upload(), "doc_type": Document.DocType.OTHER},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("organization", response.json()["error"])

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("documents:upload"))
        # login_required redirects anonymous users to the login page.
        self.assertEqual(response.status_code, 302)
