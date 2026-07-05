"""
Tests mock the BigQuery client entirely (no live BigQuery needed to run
these -- see Phase 7 guide for why there's no local BigQuery emulator).
They verify two things: correct query construction (including the mandatory
partition filter -- the cost guardrail), and correct result parsing.

Wrapped in unittest.TestCase (not bare pytest-style functions) because
Django's `manage.py test` only discovers TestCase subclasses -- a bare
`def test_...():` function is silently skipped with no error, which is
exactly the mistake this file corrects.
"""
import unittest
from unittest.mock import MagicMock, patch

from .queries import get_risk_category_distribution, get_risk_percentile


def _mock_query_job(rows):
    job = MagicMock()
    job.result.return_value = rows
    return job


class RiskPercentileQueryTests(unittest.TestCase):
    @patch("analytics.queries._get_client")
    def test_includes_partition_filter_in_sql(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query.return_value = _mock_query_job([{"percentile": 75.0, "population_size": 40}])
        mock_get_client.return_value = mock_client

        result = get_risk_percentile(doc_type="MSA", clause_type="Limitation of Liability", risk_score=90)

        sql = mock_client.query.call_args[0][0]
        self.assertIn("extracted_at >=", sql)  # the mandatory cost-guardrail partition filter
        self.assertIn("TIMESTAMP_SUB", sql)
        self.assertEqual(result, {"percentile": 75.0, "population_size": 40})

    @patch("analytics.queries._get_client")
    def test_sets_max_bytes_billed(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query.return_value = _mock_query_job([{"percentile": 50.0, "population_size": 10}])
        mock_get_client.return_value = mock_client

        get_risk_percentile(doc_type="NDA", clause_type="Confidentiality", risk_score=20)

        job_config = mock_client.query.call_args[1]["job_config"]
        self.assertEqual(job_config.maximum_bytes_billed, 100_000_000)

    @patch("analytics.queries._get_client")
    def test_returns_none_when_no_population(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query.return_value = _mock_query_job([{"percentile": None, "population_size": 0}])
        mock_get_client.return_value = mock_client

        result = get_risk_percentile(doc_type="OTHER", clause_type="Nonexistent Clause", risk_score=50)

        self.assertEqual(result["population_size"], 0)
        self.assertIsNone(result["percentile"])


class RiskCategoryDistributionQueryTests(unittest.TestCase):
    @patch("analytics.queries._get_client")
    def test_scoped_to_org_adds_filter(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query.return_value = _mock_query_job(
            [{"risk_category": "HIGH", "count": 3}, {"risk_category": "LOW", "count": 7}]
        )
        mock_get_client.return_value = mock_client

        result = get_risk_category_distribution(organization_id=1)

        sql = mock_client.query.call_args[0][0]
        self.assertIn("organization_id = @organization_id", sql)
        self.assertIn("extracted_at >=", sql)
        self.assertEqual(result, [{"risk_category": "HIGH", "count": 3}, {"risk_category": "LOW", "count": 7}])

    @patch("analytics.queries._get_client")
    def test_unscoped_omits_org_filter(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query.return_value = _mock_query_job([])
        mock_get_client.return_value = mock_client

        get_risk_category_distribution(organization_id=None)

        sql = mock_client.query.call_args[0][0]
        self.assertNotIn("organization_id", sql)
