# Validation report - 16 October 2026

## Executed locally

| Check | Result | Evidence |
|---|---|---|
| Python test suite | 38 passed, 3 skipped | evals/test-results.xml |
| Statement coverage | 84% across the Python package | pytest --cov=hybridforge run; DB/optional paths remain uncovered |
| Wheel build | Passed | hybridforge_rag-1.0.0-py3-none-any.whl built successfully |
| Live loopback HTTP smoke | Passed | evals/http-smoke.json: six documents ingested, cited query answered, UI assets HTTP 200 |
| Offline retrieval evaluation | Completed | evals/results.json, ten cases in each of three modes |
| Ruff lint and format | Passed | ruff check . and ruff format --check . |
| Frontend JavaScript syntax | Passed | node --check hybridforge/static/app.js |
| Deployment YAML parsing | Passed syntax checks | Compose, Kubernetes, alerts and CI YAML parsed locally |
| API schema generation | Passed | docs/openapi.json generated from the application factory |
| PDF review | 12 pages rendered and visually inspected | docs/HybridForge_Architecture_Handbook.pdf |

The local suite covers real SQLite transactions, ASGI API behavior, signed RSA JWT verification, mocked provider HTTP contracts and pure retrieval logic. It does not establish successful PostgreSQL or paid model execution. A Starlette TestClient deprecation warning recommends httpx2; tests currently pass with the locked httpx version. Review that migration during dependency maintenance.

## Actual offline evaluation

| Mode | Recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| Lexical | 1.00 | 1.00 | 1.00 |
| Dense hash demo | 0.40 | 0.40 | 0.40 |
| Hybrid | 1.00 | 1.00 | 1.00 |

This is a tiny synthetic regression dataset, not an independent semantic-search benchmark. Dense mode uses deterministic hash vectors; no performance inference should be made about real embedding models from these results. Raw per-case measurements are retained, including actual local timing, but those timings do not represent production latency.

## Not executed or blocked

- Three PostgreSQL tests were skipped because TEST_DATABASE_URL was absent and no PostgreSQL server was available. Installing a system server was unavailable under the environment's process permissions. The tests remain in the project and are wired into CI/Compose.
- Docker and kubectl were unavailable. YAML parsing does not validate Compose execution, Kubernetes admission, the container image or hosted behavior.
- Browser automation could not start: the Chromium binary was absent and its download returned an invalid archive. The UI assets and JavaScript syntax were verified, but rendered browser behavior, mobile layout and accessibility have not been verified in a real browser.
- Live model calls, provider account/model availability, external JWKS retrieval, key rotation, optional cross-encoder inference and OTLP export were not executed.
- No load, soak, penetration, dependency-vulnerability, backup/restore or cloud deployment test was performed.
- No repository was published and no external service was deployed.

## Reproduce and extend

Run README commands for the unit suite and offline demo. Use the disposable PostgreSQL Compose environment to execute the missing database checks. Supply real OIDC/model credentials in a staging environment for live integration. Record the deployed commit/image digest and all production acceptance evidence in PRODUCTION_READINESS.md before changing the project's readiness classification.
