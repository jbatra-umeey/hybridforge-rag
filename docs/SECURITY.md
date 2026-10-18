# Security model and threat assessment

## Trust boundaries

Browser/API clients and retrieved source text are untrusted. The identity provider, API service, model provider configuration and database administrators are trusted components. The model receives selected authorized text; its output is untrusted until structurally checked. There is no model-accessible tool execution, browsing, shell access or autonomous external action.

| Threat | Implemented control | Residual risk / release requirement |
|---|---|---|
| Client tenant spoofing | Tenant only from verified JWT; extra body fields rejected | Configure claim issuance correctly; review IdP roles |
| Cross-tenant retrieval | SQL tenant predicates, forced RLS, tenant-scoped keys | DB credentials are trusted service credentials; RLS is not a defense against full service compromise |
| Group privilege escalation | Groups from verified JWT; document RLS and API scope checks | Revoked JWT groups persist until token expiry; use short-lived tokens |
| Writer overreach | rag:write grants tenant administration explicitly | Use separate ingestion principals and narrowly grant scope |
| SQL injection | Parameterized queries; configured identifiers only in migration | No direct database access for end users |
| Stale ACL or content | Atomic document replace; no cross-request result cache | In-flight retrieval uses snapshot semantics |
| Forged citations | Source ID allowlist plus exact-quote check; whole answer rejected on failure | Claim entailment is not checked |
| Prompt injection | Evidence labeled untrusted; no tool actions; structured response | Model can still output misleading text grounded in a valid but irrelevant quote |
| XSS from evidence | UI uses textContent, never untrusted innerHTML; self-only CSP | Review any future Markdown renderer or URL-link feature |
| SSRF | No document URL fetch endpoint; provider/JWKS endpoints configured by operator | Egress restrictions and trusted endpoint configuration remain necessary |
| Resource exhaustion | 700 KB body cap, input/response limits, semaphore, bounded candidates | Add gateway timeouts and fleet-wide quotas; local quotas are evictable and reset on restart |
| Secret leakage | No raw prompts, documents, credentials or provider bodies in application event logs | Infrastructure access logs, traces and provider retention require independent review |
| Supply-chain compromise | Runtime/dev dependency hash locks and nonroot container configuration | Vulnerability scanning, base-image digests, action SHA pins and optional model pinning are release gates |

## PostgreSQL policies

Documents are readable when tenant matches and either ACL is empty, a group overlaps, or the principal has writer scope. Only writers can insert/delete within the same tenant. Chunk SELECT checks the visible parent document. Transaction-local settings hold tenant, groups and can_write; they reset after commit/rollback, preventing pooled connection state leakage. The application refuses a superuser or BYPASSRLS role and verifies forced RLS is enabled.

A trusted service can change custom PostgreSQL settings. These policies protect against missing tenant predicates and ordinary API authorization mistakes, not against an attacker with the application DB password or arbitrary SQL execution. Keep that password in a secret manager; allow network access only from the application tier.

## Token and transport policy

Use RS256 access tokens scoped to this API. Validate issuer and audience exactly. JWKS URL is explicitly configured and not inferred from untrusted token fields. JWKS is cached for five minutes; key retrieval failures reject authentication. Set access-token lifetime according to revocation requirements. Do not expose demo mode outside a developer loopback environment.

Use TLS at ingress and `sslmode=verify-full` to PostgreSQL. The code validates HTTPS for model and identity endpoints, but database TLS and gateway TLS are operator requirements rather than fully enforced environment checks. Set a trusted CA path and test certificate mismatch failures before release.

## Data handling

Only selected passages and the question go to generation, while document chunks go to the embedding provider during ingestion. Obtain permission to process the corpus with that provider, define regional/retention requirements, and configure provider logging appropriately. This project does not perform PII redaction, malware scanning, legal retention or automated data classification. All bundled data is fictional.

Deleting a document removes the active database rows and future retrieval access. It does not delete copies already returned to clients, model-provider logs, database backups or telemetry added by operators. Define backup expiration and deletion procedures for compliance-sensitive use.

## Security qualification checklist

- Exercise tenant and group negative tests against the deployed PostgreSQL role.
- Verify JWT algorithm confusion, expired/malformed claims and wrong audience fail closed.
- Test role removal and membership changes through your real identity provider.
- Red-team source injection, misleading exact quotes and source contradictions.
- Probe payload limits, gateway slow-request handling and distributed quota enforcement.
- Verify no prompt/token leakage in application, proxy and trace stores.
- Perform dependency/container scanning and a targeted external security review.
