-- Read-only ingestion capacity and recovery diagnostics.
-- Run against a restored copy when investigating corruption.

-- Raw artifact retention and wrapping-key inventory.
SELECT artifact_state,
       artifact_key_version,
       count(*) AS documents,
       coalesce(sum(size_bytes), 0) AS source_bytes,
       min(raw_retained_until) AS earliest_retention_deadline
FROM documents
GROUP BY artifact_state, artifact_key_version
ORDER BY artifact_state, artifact_key_version;

-- Storage used by durable ingestion tables (indexes included).
SELECT relname,
       pg_total_relation_size(relid) AS total_bytes
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN (
  'documents', 'processing_runs', 'chunks', 'content_derivations', 'content_blocks',
  'chunk_block_spans', 'processing_derivations', 'source_items', 'source_revisions',
  'source_snapshots', 'source_snapshot_members', 'ingestion_runs',
  'ingestion_run_items', 'index_versions', 'index_chunks', 'query_runs',
  'experiments', 'experiment_items'
)
ORDER BY total_bytes DESC, relname;

-- Job backlog and age. Investigate running work older than the configured stale fence.
SELECT 'processing' AS job_kind, status, count(*) AS jobs,
       min(updated_at) AS oldest_update
FROM processing_runs GROUP BY status
UNION ALL
SELECT 'index', status, count(*), min(updated_at)
FROM index_versions GROUP BY status
UNION ALL
SELECT 'ingestion', status, count(*), min(updated_at)
FROM ingestion_runs GROUP BY status
ORDER BY job_kind, status;

-- Safe reprocessing estimate: exact retained source bytes and already saved chunks.
WITH retained AS (
  SELECT project_id, count(*) AS documents, sum(size_bytes) AS retained_source_bytes
  FROM documents WHERE artifact_state = 'encrypted' GROUP BY project_id
), saved AS (
  SELECT d.project_id, count(c.ordinal) AS saved_chunks
  FROM documents d
  JOIN processing_runs r ON r.document_id = d.id AND r.status = 'succeeded'
  JOIN chunks c ON c.run_id = r.id
  GROUP BY d.project_id
)
SELECT p.id AS project_id,
       coalesce(retained.documents, 0) AS documents,
       coalesce(retained.retained_source_bytes, 0) AS retained_source_bytes,
       coalesce(saved.saved_chunks, 0) AS saved_chunks
FROM projects p
LEFT JOIN retained ON retained.project_id = p.id
LEFT JOIN saved ON saved.project_id = p.id
ORDER BY p.id;

-- Integrity diagnostics; every count must be zero.
SELECT count(*) AS orphan_processing_derivations
FROM processing_derivations pd
LEFT JOIN processing_runs r ON r.id = pd.run_id
WHERE r.id IS NULL;

SELECT count(*) AS ready_indexes_with_incomplete_counts
FROM index_versions
WHERE status = 'succeeded'
  AND (embedded_count <> total_chunks OR failed_count <> 0);

SELECT count(*) AS deleted_artifacts_with_live_envelopes
FROM documents
WHERE artifact_state = 'deleted'
  AND (artifact_wrapped_key IS NOT NULL OR artifact_key_version IS NOT NULL);

-- Sensitive reads contain identities and resource IDs, never source values.
SELECT project_id, action, outcome, count(*) AS events,
       min(created_at) AS first_event, max(created_at) AS last_event
FROM sensitive_access_events
GROUP BY project_id, action, outcome
ORDER BY project_id, action, outcome;
