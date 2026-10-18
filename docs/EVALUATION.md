# Evaluation strategy

## Delivered automation

The runner loads six fictional engineering documents and ten labeled questions. It computes document-level Recall@5, MRR and nDCG@5 for lexical, dense and hybrid modes. Duplicate chunks are collapsed by document before metrics. Each case records retrieved IDs and retrieval latency. The stored evals/results.json contains the actual local result.

Offline evaluations use deterministic hash embeddings and extractive responses. They validate plumbing and regressions, not semantic understanding or model superiority. The questions intentionally reference the sample corpus; this small in-sample suite is not sufficient for deployment claims. The restricted executive document is tested separately for permissions.

```bash
python scripts/evaluate.py --output evals/results.json
RAG_TOKEN='access-token' python scripts/evaluate.py --api-url https://rag.example.com --output evals/live-results.json
```

The API mode expects the same sample IDs already seeded and visible to its token. It measures retrieval only, not generation quality. A real test corpus should replace both the documents and labels and use reader tokens representing realistic ACLs.

## Production study design

Create a held-out dataset with exact product codes, paraphrases, ambiguous questions, multi-document answers, negative questions, stale/contradictory policies, multilingual content and prompt-injected documents. Split by source document family and time, not only by question string, to reduce leakage. Have domain experts label answerability, relevant passages and expected facts.

Compare lexical-only, dense-only, hybrid and hybrid-plus-cross-encoder under identical ACLs, budgets and hardware. Calibrate chunk size, overlap, dense threshold, candidate count and reranker on a separate development set. Report gains and regressions per query category; do not hide poorer hybrid cases behind a macro average.

| Layer | Metrics / checks | Proposed gate, to agree with stakeholders |
|---|---|---|
| Retrieval | Recall@5, nDCG@5, MRR, empty-result rate | No critical identifier regressions; relative target chosen from baseline |
| Authorization | Tenant/group leakage, ACL changes, pool reuse | Zero unauthorized chunks in adversarial suite |
| Generation | Supported-claim rate, answer completeness, refusal correctness | Human-reviewed threshold by risk class |
| Citations | Correct source, exact quote, semantic entailment | Zero invalid IDs/quotes; independent entailment review |
| Reliability | Provider timeouts, 429s, DB restart and recovery | Errors are bounded and preserve previous committed documents |
| Performance | p50/p95/p99, concurrency, memory, cost per query | Capacity proven at agreed load and corpus size |
| Operations | Backup restore, secret rotation, rollout/rollback | Successful drills recorded before production |

Citation presence is not faithfulness. A valid quote can be irrelevant to the model's claim. Use human adjudication and optionally an independently calibrated entailment judge; avoid relying on the same generator to approve its own claims. Record disagreement and judge calibration.

## Automated tests

The delivered suite covers chunk boundaries, fusion, context limits, API authentication, input/body bounds, tenant/group isolation, idempotency, concurrent writers, stale versions, atomic failure handling, invalid citations, OIDC claim validation and provider HTTP contracts. PostgreSQL-specific tests exercise RLS without relying only on application predicates, pooled-context reset, group filtering and lifecycle behavior. They must run on a migrated test database as rag_app, not as postgres.

## Experiment record

For each qualification run retain commit SHA, dependency lock hash, DB/extension versions, model and optional reranker revision, corpus fingerprint, question split, JWT entitlement profile, configuration, hardware, results and reviewer sign-off. Never place real prompts, restricted documents or access tokens into a public repository.
