# Architecture decision records

## ADR-001: One transactional retrieval store

**Decision:** PostgreSQL stores metadata, chunks, full-text representation and vectors. **Reason:** one transaction can replace content, ACL and embeddings together; no dual-write synchronization layer is needed. **Tradeoff:** specialized search engines may provide better BM25 features or large-scale ANN throughput. Reconsider after measured retrieval/capacity gaps, not because of feature lists.

## ADR-002: Reciprocal rank fusion

**Decision:** sum equal-weight reciprocal ranks with k=60. **Reason:** lexical and vector scores have different ranges and interpretations. **Tradeoff:** RRF discards score magnitude and does not calibrate confidence. Tune with held-out labels; weighted fusion can be added when justified.

## ADR-003: Exact authorized-subset dense retrieval

**Decision:** use exact pgvector similarity over a materialized authorized subset in v1. **Reason:** predictable filtering and a clear correctness baseline. **Tradeoff:** linear scan cost; not suited to unbounded corpora. ANN requires a query redesign plus filtered-recall validation. A cosmetic HNSW index is not presented as a scaling implementation.

## ADR-004: Tenant administrator ingestion

**Decision:** rag:write permits tenant-wide administration; ordinary readers are constrained by groups. **Reason:** clear ownership for ingestion and ACL changes. **Tradeoff:** no document-owner write ACL. If needed, add a separate ownership policy and tests before offering user-managed collections.

## ADR-005: Synchronous bounded ingestion

**Decision:** finish embedding and a transactional commit before replying. **Reason:** a small, runnable deployment with explicit failure behavior and no false async guarantees. **Tradeoff:** large batches need a durable queue, job leasing, retries and cancellation; these remain extensions.

## ADR-006: Structured claims and exact quotes

**Decision:** require each generated claim to identify a retrieved chunk and quote it exactly. **Reason:** deterministic provenance validation and useful failure behavior. **Tradeoff:** valid provenance does not imply entailment. The project makes that limitation visible in its API and UI.

## ADR-007: Explicit offline adapter

**Decision:** provide hash-vector + BM25 retrieval and evidence-only extraction for no-key demos. **Reason:** reproducible testing without transmitting user data or calling paid models. **Tradeoff:** no semantic capability or production quality claim from offline scores. Production selects a different provider and storage adapter explicitly.

## ADR-008: No answer cache or conversational memory in v1

**Decision:** each request retrieves current authorized evidence independently. **Reason:** avoids cache permission leakage and memory retention complexity. **Tradeoff:** repeated questions cost model calls. Any future cache key must include tenant, entitlement version, corpus version, model and generation configuration; revocation invalidation must be designed.
