# Production acceptance checklist

**Current classification: executable production-oriented reference implementation. Production acceptance is not established.** The presence of source code, a passing local suite, or Kubernetes YAML is not equivalent to deployment verification.

| Gate | Delivered artifact | Required before production |
|---|---|---|
| Functional correctness | Unit/API tests and offline evaluation | Run PostgreSQL integration, validate real embedding/generation behavior |
| Identity | OIDC verifier and negative-token tests | Real issuer integration, key rotation, audience and entitlement review |
| Data isolation | RLS migration and three database tests | Execute against deployed role; tenant/ACL adversarial test suite |
| Retrieval quality | Hybrid pipeline and ablation runner | Held-out labeled enterprise corpus, threshold/candidate calibration |
| Generation quality | Citation validator and abstention | Entailment/faithfulness review, adversarial/contradictory source tests |
| Supply chain | Hash-locked runtime/dev dependencies | Vulnerability/SBOM scan, image digest and action SHA pins, model revision lock |
| Transport/secrets | Configuration examples and hardened pod spec | TLS ingress, DB certificate verification, secret manager and rotation drills |
| Capacity | Input/operation bounds and telemetry | Load/soak tests, corpus-size capacity limits, distributed quotas |
| Resilience | Atomic writes, provider retry bounds | Failure injection, provider outage tests, DB restart and restore drills |
| Operations | Metrics, traces, alert rules and runbook | Working collector/scraper, alert routing, on-call ownership |
| Governance | Threat model and data-flow description | Data classification, provider retention/region review, deletion policy |
| Delivery | Docker/Compose/Kubernetes and CI templates | Build/scan image, execute CI, stage, canary and rollback |

## Known limits

- Production PostgreSQL tests could not execute in the creation environment; a server and Docker were unavailable.
- Real paid model calls, real JWKS retrieval and optional cross-encoder inference were not executed.
- No application image has been built, pushed, scanned or deployed here.
- No source connector, PDF/OCR parser, durable ingestion queue, immutable revision archive or conversation memory.
- Exact dense scans require measured corpus limits. No ANN speed or scale claims are supported.
- Per-process quotas are not global; admission rejects rather than queues when all slots are busy.
- Provider timeouts are phase-based; there is no hard workflow deadline, cancellation propagation or circuit breaker.
- Database/ingress TLS and provider data policy require operator configuration.
- Optional reranker dependencies are outside the validated lockfiles.
- Citation checks verify source/quote structure only; source truth and semantic support require additional evaluation.

## Acceptance sign-off record

Record the owner, date, environment, commit/image digest, evidence link and outcome for every gate. A security owner signs identity/isolation; a domain owner signs answer quality; an SRE owner signs capacity/recovery; a product owner accepts residual limitations. Any unmet gate should block a production-readiness claim.
