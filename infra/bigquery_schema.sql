-- Phase 7: the population-analytics table. One row per clause, streamed by
-- ai_service after every successfully processed document (Phase 6's
-- COMPLETE path). This is the platform's OWN accumulated usage data -- a
-- completely different "population" from Phase 4's CUAD corpus (which lives
-- in ChromaDB and seeds risk-scoring RAG comparisons). Don't confuse the two.
--
-- Partitioned by day (extracted_at) and clustered by doc_type/clause_type so
-- that every population query in analytics/queries.py can filter on both --
-- partition pruning + clustering together keep query cost low even as this
-- table grows into the millions of rows.

CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}`
OPTIONS (location = '{location}');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.processed_clauses` (
  clause_id             STRING    NOT NULL,  -- deterministic: "{job_id}-{clause_index}"
  job_id                INT64     NOT NULL,
  document_id           INT64     NOT NULL,
  organization_id       INT64     NOT NULL,
  doc_type              STRING    NOT NULL,
  clause_type           STRING    NOT NULL,
  clause_text           STRING,
  risk_score            FLOAT64,             -- NULL for doc types that skip risk scoring (NDA)
  risk_category         STRING,              -- LOW / MEDIUM / HIGH / NULL
  template_match_source STRING,
  template_similarity   FLOAT64,
  extracted_at          TIMESTAMP NOT NULL
)
PARTITION BY DATE(extracted_at)
CLUSTER BY doc_type, clause_type;
