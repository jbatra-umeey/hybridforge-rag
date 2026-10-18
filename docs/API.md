# API contract

Base URL in the demo: `http://127.0.0.1:8000`. JSON requests and responses use UTF-8. The generated schema is available at `/openapi.json` and as `docs/openapi.json`. External-CDN API documentation is disabled to retain a strict self-only content security policy.

| Route | Authorization | Behavior |
|---|---|---|
| GET / | Public | Browser workbench shell; no document data |
| GET /health/live | Public | Process liveness and selected mode |
| GET /health/ready | Public | Database/schema readiness; does not probe model API |
| GET /metrics | rag:observe | Prometheus metrics across this process |
| GET /v1/documents | rag:read | Authorized document metadata; PG maximum 1,000 rows |
| PUT /v1/documents | rag:write | Create or atomically replace one document |
| DELETE /v1/documents/{id}?expected_version=N | rag:write | Delete current revision and chunks |
| POST /v1/search | rag:read | Ranked selected evidence with diagnostics |
| POST /v1/query | rag:read | Grounded claims, citations and retrieval diagnostics |

## Identity

Pass `Authorization: Bearer ACCESS_TOKEN`. Production requires RS256, the configured issuer and audience, expiry, issued-at, subject and tenant_id. `groups` is an array of at most 32 identifiers, `scope` is a space-delimited string. Token tenant and groups must be issued by a trusted identity system, never copied from arbitrary client metadata. Do not accept an ID token intended for a different audience.

Identifiers use `[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}`. Empty document ACL groups mean all readers in that tenant, not anonymous/public access. `rag:write` implies administrative visibility inside that tenant, but API read routes still require `rag:read`.

## Create / replace

```json
{
  "document_id": "release-guide",
  "title": "Release guide",
  "source": "handbook/releases.md",
  "text": "Rollback when the approved release threshold is exceeded.",
  "acl_groups": ["engineering"],
  "expected_version": 0
}
```

Use expected_version=0 for a new ID, then the current version for changed replacements. Response fields: document_id, version, changed, and chunks for a changed write. Repeating identical fields is idempotent; it can still incur embedding API usage because fingerprint comparison occurs inside the write transaction after embedding. A failed model call leaves storage unchanged.

The text limit is 100,000 characters; the outer HTTP body limit is 700,000 bytes and the derived chunk limit is 128. The source field is a label, not a URL to crawl. Accepted text is not sanitized into HTML and is rendered with textContent. File paths, remote fetching and document parsers are outside this API.

## Query

```json
{"question":"ERR_BRIDGE_042", "mode":"hybrid", "top_k":5, "candidate_k":30}
```

Modes: hybrid, lexical, dense. The response contains status (`answered` or `abstained`), reason, plain-text answer, citations, selected evidence, diagnostics, generation_mode and request_id. Source citations include document_id, version, title, source, exact quote and the full chunk's start/end character offsets. Offsets identify the chunk, not the substring occupied by the quote. Numbered references in the answer map to the citations array.

Search results include RRF score, lexical/dense rank when present, and optional reranker score. These are ranking signals, not confidence values. The returned evidence is scoped to the caller. No previous chat history is supplied to the model.

## Failure handling

| HTTP | Meaning | Caller action |
|---|---|---|
| 401 | Missing/invalid/expired token | Obtain a valid access token |
| 403 | Missing required scope | Request the correct permission |
| 409 | Missing or stale document revision | Refresh metadata; do not blindly overwrite |
| 413 | Body too large | Split the document |
| 422 | Invalid fields or bounded-input violation | Correct the payload |
| 429 | Per-process subject quota exhausted | Wait; Retry-After is returned |
| 502 | Provider failure or invalid citations | Retry with backoff; inspect request ID |
| 503 | Capacity or storage failure | Retry with backoff and investigate service health |

Schema validation responses can echo invalid input; clients should avoid putting secrets into unexpected fields. No CORS origins are enabled by default. The supplied UI uses the same origin as the API.

## Client-side retry policy

Retry transport failures and 429/502/503 with exponential backoff and jitter, respecting Retry-After. Cap attempts and total deadline. Generation retries can incur additional model charges. Do not retry authentication errors or version conflicts automatically. Long synchronous ingestion should use an explicit larger client timeout; a durable ingestion queue is not included.
