"""
Tests for the production Pub/Sub push webhook. id_token.verify_oauth2_token
is mocked — verifying real Google-signed tokens requires a live token,
which isn't available in a test environment. These tests verify the
authorization logic (missing/invalid/wrong-service-account tokens are all
rejected) and the envelope parsing, using apply_processed_event mocked out
so this stays a unit test of the view, not an integration test of the
whole pipeline (that's what Phase 6/9's manual end-to-end tests are for).
"""
import base64
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


def _push_body(payload: dict) -> bytes:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    envelope = {"message": {"data": data, "messageId": "test-1"}, "subscription": "test-sub"}
    return json.dumps(envelope).encode("utf-8")


@override_settings(AI_SA_EMAIL="ai-worker-sa@test-project.iam.gserviceaccount.com")
class ProcessedEventWebhookTests(TestCase):
    def test_missing_authorization_header_is_forbidden(self):
        response = self.client.post(
            reverse("documents:processed_webhook"),
            data=_push_body({"job_id": 1, "status": "COMPLETE"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    @patch("documents.views.id_token.verify_oauth2_token")
    def test_invalid_token_is_forbidden(self, mock_verify):
        mock_verify.side_effect = ValueError("bad token")
        response = self.client.post(
            reverse("documents:processed_webhook"),
            data=_push_body({"job_id": 1, "status": "COMPLETE"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer faketoken",
        )
        self.assertEqual(response.status_code, 403)

    @patch("documents.views.id_token.verify_oauth2_token")
    def test_token_from_wrong_service_account_is_forbidden(self, mock_verify):
        mock_verify.return_value = {"email": "someone-else@evil.iam.gserviceaccount.com"}
        response = self.client.post(
            reverse("documents:processed_webhook"),
            data=_push_body({"job_id": 1, "status": "COMPLETE"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer faketoken",
        )
        self.assertEqual(response.status_code, 403)

    @patch("documents.views.apply_processed_event")
    @patch("documents.views.id_token.verify_oauth2_token")
    def test_valid_token_and_payload_applies_event(self, mock_verify, mock_apply):
        mock_verify.return_value = {"email": "ai-worker-sa@test-project.iam.gserviceaccount.com"}
        response = self.client.post(
            reverse("documents:processed_webhook"),
            data=_push_body({"job_id": 42, "status": "COMPLETE", "result": {"clauses": []}}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer validtoken",
        )
        self.assertEqual(response.status_code, 204)
        mock_apply.assert_called_once_with({"job_id": 42, "status": "COMPLETE", "result": {"clauses": []}})

    @patch("documents.views.id_token.verify_oauth2_token")
    def test_malformed_envelope_is_bad_request(self, mock_verify):
        mock_verify.return_value = {"email": "ai-worker-sa@test-project.iam.gserviceaccount.com"}
        response = self.client.post(
            reverse("documents:processed_webhook"),
            data=json.dumps({"not_a_message": {}}).encode("utf-8"),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer validtoken",
        )
        self.assertEqual(response.status_code, 400)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("documents:processed_webhook"))
        self.assertEqual(response.status_code, 405)
