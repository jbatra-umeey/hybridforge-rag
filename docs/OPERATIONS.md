# Deployment and operations runbook

## Environments and release path

Local demo -> disposable PostgreSQL integration -> staging with real OIDC/models -> canary -> wider production. Promotion requires the gates in PRODUCTION_READINESS.md. The reference Kubernetes YAML is an application-tier template. It intentionally does not create a database, ingress controller, identity provider, certificate authority or external secrets system.

1. Build and scan a container from the tested commit. Pin its digest and the Python/PostgreSQL base image digests. Record the SBOM, dependency locks and model identifiers.
2. Provision PostgreSQL 17 with pgvector >=0.8, encrypted disks, backups and WAL archiving. Create the database. Enforce TLS and restrict network access.
3. Run scripts/migrate.py with an owner/migration DSN and a strong RAG_DB_PASSWORD. Do not give that DSN to the serving deployment. For an existing rag_app role, rotate credentials separately.
4. Supply the application configuration through a secret manager. The Kubernetes template expects a `hybridforge-config` Secret with DATABASE_URL, OPENAI_API_KEY, OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL. Supply `hybridforge-db-ca` with ca.crt. Never commit either Secret.
5. Customize registry image, namespace selectors and egress destinations. Use a TLS gateway with request/body/idle deadlines, fleet-wide subject/tenant quotas and trusted proxy configuration.
6. Start two replicas; check readiness, then run authenticated ingestion/search/generation smoke tests. Readiness proves storage connectivity and schema controls, not model reachability.
7. Seed only approved documents, run live retrieval and answer-quality evaluations, inspect telemetry, and progressively route traffic.

## Capacity and timeout model

The default process permits eight RAG operations at once and keeps up to twelve PostgreSQL connections. With two replicas that permits up to sixteen simultaneous operations and twenty-four pooled DB connections; add reserve capacity for migrations and administrators. One uvicorn worker per container is the reference deployment. Multiple workers multiply these limits and produce separate metrics registries.

Model requests use a 5-second connect timeout and 25-second phase timeout, with up to three attempts for transient failures. These are HTTP phase timeouts, not a hard end-to-end deadline. Ingestion can contain up to four embedding batches and exceed a typical short gateway timeout. For production bulk workloads, add a durable job queue with cancellation, deadlines, retries and a dead-letter queue; that facility is not included. Do not call the synchronous endpoint an asynchronous ingestion system.

The v1 exact dense scan is linear in the number of authorized chunks. Benchmark p50/p95/p99 by tenant size and permission selectivity. If capacity is insufficient, evaluate tenant partitioning or an ANN query redesign with recall regression tests. Increasing connection pools is not a substitute for measuring CPU, memory, locks and retrieval cost.

## Telemetry

The application exposes `rag_operations_total{operation,outcome}` and `rag_operation_seconds{operation}`. Labels are bounded and exclude tenant, subject, document and request IDs. Authentication/rate-limit rejections that occur before an operation are not counted in these metrics; gateway metrics should cover total HTTP traffic.

OTLP export is enabled only when OTEL_EXPORTER_OTLP_ENDPOINT is set. Spans cover query/document embeddings, storage, retrieval, reranking and generation. Do not add prompt or source attributes. Application operation logs contain request_id, operation and outcome; external access logs should follow your privacy policy. Scrape /metrics using a short-lived rag:observe token and protected network access. Monitor token refresh for the scraper.

Alert examples are in deploy/prometheus-alerts.yaml. Their thresholds are provisional: query p95 >15 seconds and errors >5 percent are starting points, not demonstrated SLOs. The synthetic offline evaluation is not a latency benchmark.

## Incident playbooks

| Symptom | First checks | Mitigation |
|---|---|---|
| 401 spike | Issuer/audience config, token expiry, JWKS egress and rotation | Correct identity configuration; never disable verification |
| 403 spike | Token scopes and source ACL changes | Restore intended entitlement through approved identity workflow |
| 502 spike | Provider status, quota, structured-output compatibility | Back off; adjust approved model config; preserve fail-closed behavior |
| 503 or slow search | Pool use, PG statement timeout, authorized corpus size, provider latency | Reduce admission load; scale only after finding bottleneck |
| Empty evidence | Tenant/groups, embedding_id mismatch, lexical query semantics, threshold | Verify authorized source ingestion and reindex state |
| Irrelevant answer | Evidence ranking, source quality, quote/claim mismatch | Quarantine source or disable generation; run quality regression |
| Version conflicts | Competing ingestion writers, stale expected_version | Re-read current version; serialize upstream ingestion |
| Suspected data leak | Identity mapping, DB role grants, logs and returned citations | Stop exposure, revoke credentials, preserve restricted evidence and follow incident policy |

## Backup and recovery

Set RPO/RTO with the business; illustrative targets are RPO 15 minutes/RTO 60 minutes and are not verified guarantees. Use physical backups plus WAL archiving for PostgreSQL. Test a restore to an isolated environment, confirm extension version, role grants, forced RLS, document/chunk counts and source digests, then run tenant-negative and retrieval tests. Rebuild indexes as needed. A successful backup command does not establish recoverability.

Before rollback, verify application/schema compatibility. Schema v1 is additive installation only and has no destructive down migration. Restore the previous image while keeping schema v1 if compatible; otherwise use the tested recovery procedure. Never drop production content to resolve an application deployment problem.

## Embedding/model changes

Embedding identity includes model name and dimensions. Search filters to the current identity; changing it without reindexing makes old documents disappear from retrieval. For a small corpus, reingest all documents with current expected versions during a controlled window. For zero-downtime large-corpus migration, implement dual indexes and an atomic active-index alias before changing models. That workflow is a documented extension, not an implemented feature.

## Cost planning

Estimate ingestion cost from total embedded tokens, including overlapping chunks and repeated idempotent writes. Query cost includes query embeddings and selected-context generation. Budget retries and reranking compute. This build does not meter monetary cost or enforce organization-wide spend. Use provider billing limits and gateway budgets; measure actual token usage before setting commercial limits.
