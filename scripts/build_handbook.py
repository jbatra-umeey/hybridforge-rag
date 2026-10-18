"""Generate editable SVG diagrams and a concise PDF handbook. Requires reportlab 4.4.9."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
INK = colors.HexColor("#153441")
TEAL = colors.HexColor("#087f83")
MINT = colors.HexColor("#dff5ed")
MUTED = colors.HexColor("#536e79")
LINE = colors.HexColor("#d6e4e5")
PALE = colors.HexColor("#f1f6f6")


def label(d, x, y, text, size=13, color=INK, bold=False):
    d.add(
        String(
            x,
            y,
            text,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,
            fillColor=color,
        )
    )


def box(d, x, y, w, h, title, sub="", accent=False):
    d.add(
        Rect(
            x,
            y,
            w,
            h,
            rx=10,
            ry=10,
            fillColor=MINT if accent else colors.white,
            strokeColor=TEAL if accent else LINE,
            strokeWidth=1.2,
        )
    )
    label(d, x + 15, y + h - 27, title, 14, bold=True)
    for i, line in enumerate(sub.split("|")):
        label(d, x + 15, y + h - 49 - i * 17, line, 10.5, MUTED)


def arrow(d, x1, y1, x2, y2):
    import math

    d.add(Line(x1, y1, x2, y2, strokeColor=TEAL, strokeWidth=1.6))
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 7
    points = [
        x2,
        y2,
        x2 - size * math.cos(angle - 0.45),
        y2 - size * math.sin(angle - 0.45),
        x2 - size * math.cos(angle + 0.45),
        y2 - size * math.sin(angle + 0.45),
    ]
    d.add(Polygon(points, fillColor=TEAL, strokeColor=TEAL))


def background(w, h, title, subtitle):
    d = Drawing(w, h)
    d.add(Rect(0, 0, w, h, fillColor=PALE, strokeColor=None))
    label(d, 30, h - 42, title, 22, bold=True)
    label(d, 30, h - 65, subtitle, 11, MUTED)
    return d


def architecture():
    d = background(
        800,
        760,
        "Retrieval with an explicit evidence trail",
        "Production path: PostgreSQL + learned embeddings + structured generation",
    )
    box(d, 245, 600, 310, 70, "Authenticated request", "JWT tenant, groups and scopes", True)
    arrow(d, 400, 600, 400, 565)
    box(
        d,
        245,
        485,
        310,
        80,
        "Query embedding + policy scope",
        "Configured embedding model|Tenant/ACL checks in PostgreSQL",
    )
    arrow(d, 320, 485, 205, 440)
    arrow(d, 480, 485, 595, 440)
    box(
        d, 55, 350, 300, 90, "Lexical retrieval", "tsvector + GIN|websearch_to_tsquery + ts_rank_cd"
    )
    box(
        d,
        445,
        350,
        300,
        90,
        "Dense retrieval",
        "pgvector cosine similarity|Exact search over authorized rows",
    )
    arrow(d, 205, 350, 330, 305)
    arrow(d, 595, 350, 470, 305)
    box(
        d,
        245,
        225,
        310,
        80,
        "Reciprocal rank fusion",
        "Optional cross-encoder rerank|Deduplicate + bound evidence context",
        True,
    )
    arrow(d, 400, 225, 400, 190)
    box(d, 245, 110, 310, 80, "Grounded generation", "Structured claims + exact source quotes")
    arrow(d, 245, 150, 210, 150)
    arrow(d, 555, 150, 590, 150)
    box(d, 35, 105, 175, 90, "Validate + answer", "Known IDs and quotes|Return cited claims")
    box(d, 590, 105, 175, 90, "Abstain / fail", "No usable evidence|Invalid provider output")
    label(
        d,
        35,
        47,
        "Security scope applies before candidate fusion and before sending text to the model.",
        11,
        MUTED,
    )
    label(
        d,
        35,
        28,
        "Quote validation checks provenance. It does not prove that a claim follows from the quote.",
        11,
        MUTED,
    )
    return d


def ingestion():
    d = background(
        800,
        650,
        "Atomic document replacement",
        "Embeddings are prepared before opening the database write transaction",
    )
    box(
        d,
        50,
        460,
        300,
        95,
        "Validate + fingerprint",
        "Text, title, source, ACLs|Expected version + embedding identity",
    )
    box(
        d,
        450,
        460,
        300,
        95,
        "Chunk + embed",
        "1,200 characters / 180 overlap|Up to 32 chunks per provider request",
    )
    arrow(d, 350, 508, 450, 508)
    arrow(d, 600, 460, 600, 407)
    d.add(Rect(35, 110, 730, 295, rx=13, fillColor=MINT, strokeColor=TEAL))
    label(d, 55, 375, "ONE DATABASE TRANSACTION", 12, TEAL, True)
    box(
        d,
        70,
        245,
        290,
        95,
        "Check retry / conflict",
        "Same fingerprint: unchanged|Stale version: reject with HTTP 409",
    )
    box(
        d,
        440,
        245,
        290,
        95,
        "Acquire document lock",
        "Tenant + document advisory lock|Read current version and fingerprint",
    )
    arrow(d, 600, 407, 585, 340)
    arrow(d, 440, 290, 360, 290)
    box(
        d,
        250,
        135,
        300,
        75,
        "Replace rows + commit",
        "Delete old chunks and insert new revision",
        True,
    )
    arrow(d, 215, 245, 325, 210)
    label(
        d,
        40,
        67,
        "Failure before commit: the prior committed document remains available.",
        12,
        INK,
        True,
    )
    label(
        d,
        40,
        43,
        "Active revisions are versioned; historical source bodies are not archived in v1.",
        11,
        MUTED,
    )
    return d


def deployment():
    d = background(
        800,
        710,
        "Production topology and ownership",
        "Application templates are delivered; hosted infrastructure is operator-provisioned",
    )
    box(d, 245, 550, 310, 75, "TLS gateway", "Global quotas, request limits, deadlines", True)
    arrow(d, 330, 550, 210, 500)
    arrow(d, 470, 550, 590, 500)
    box(d, 55, 420, 310, 80, "API replica A", "Nonroot container | OIDC verification")
    box(d, 435, 420, 310, 80, "API replica B", "Stateless serving | bounded concurrency")
    arrow(d, 210, 420, 310, 360)
    arrow(d, 590, 420, 490, 360)
    box(
        d,
        240,
        265,
        320,
        95,
        "PostgreSQL + pgvector",
        "Forced RLS | tenant-scoped rows|Separate migration and serving roles",
        True,
    )
    box(
        d,
        35,
        120,
        215,
        90,
        "Model provider",
        "Embedding and generation|Approved data-processing region",
    )
    box(d, 295, 120, 215, 90, "Telemetry", "Prometheus + OTLP|No source or prompt payloads")
    box(
        d, 555, 120, 215, 90, "Backup / recovery", "Encrypted backups + WAL|Restore drills required"
    )
    arrow(d, 100, 420, 140, 210)
    d.add(Line(700, 420, 700, 235, strokeColor=TEAL, strokeWidth=1.6))
    d.add(Line(700, 235, 405, 235, strokeColor=TEAL, strokeWidth=1.6))
    arrow(d, 405, 235, 405, 210)
    arrow(d, 560, 290, 660, 210)
    label(
        d,
        35,
        65,
        "Identity, ingress, secrets, database hosting and observability are external dependencies.",
        11,
        MUTED,
    )
    label(
        d,
        35,
        42,
        "The supplied manifests have not been deployed or load-tested in this delivery.",
        11,
        TEAL,
        True,
    )
    return d


def data_model():
    d = background(
        800,
        470,
        "Tenant-scoped relational model",
        "A document and its lexical/vector chunks commit together",
    )
    box(
        d,
        40,
        100,
        300,
        260,
        "DOCUMENTS",
        "PK tenant, document_id|version, digest|title, source|acl_groups[]|embedding_id|updated_at",
        True,
    )
    box(
        d,
        460,
        100,
        300,
        260,
        "CHUNKS",
        "PK tenant, chunk_id|FK tenant, document_id|version, title, source|body, start_char, end_char|embedding vector(1536)|generated search_vector",
        True,
    )
    arrow(d, 340, 230, 460, 230)
    label(d, 365, 248, "1 to many", 10, MUTED)
    label(
        d,
        40,
        57,
        "Foreign key cascade deletes active chunks. Both content tables FORCE row-level security.",
        11,
        MUTED,
    )
    return d


styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="Kicker",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=TEAL,
        spaceAfter=12,
    )
)
styles.add(
    ParagraphStyle(
        name="TitleHF",
        fontName="Helvetica-Bold",
        fontSize=29,
        leading=34,
        textColor=INK,
        spaceAfter=18,
    )
)
styles.add(
    ParagraphStyle(
        name="BodyHF", fontName="Helvetica", fontSize=10, leading=15, textColor=INK, spaceAfter=10
    )
)
styles.add(
    ParagraphStyle(
        name="SmallHF",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=MUTED,
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="HeadHF",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=19,
        textColor=INK,
        spaceBefore=10,
        spaceAfter=9,
    )
)
styles.add(
    ParagraphStyle(name="TableHF", fontName="Helvetica", fontSize=8.4, leading=12, textColor=INK)
)
styles.add(
    ParagraphStyle(
        name="TableHeadHF",
        fontName="Helvetica-Bold",
        fontSize=8.6,
        leading=12,
        textColor=colors.white,
    )
)
story = []


def p(text, style="BodyHF"):
    story.append(Paragraph(text, styles[style]))


def title(n, text, sub):
    if story:
        story.append(PageBreak())
    p("HYBRIDFORGE / ENGINEERING HANDBOOK / " + n, "Kicker")
    p(text, "TitleHF")
    p(sub, "SmallHF")
    story.append(Spacer(1, 9))


def heading(text):
    p(text, "HeadHF")


def table(headers, rows, widths):
    data = [[Paragraph(escape(x), styles["TableHeadHF"]) for x in headers]]
    data += [[Paragraph(escape(str(x)), styles["TableHF"]) for x in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALE, colors.white]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 12))


def diagram(d, width=493):
    factor = width / d.width
    d.scale(factor, factor)
    d.width *= factor
    d.height *= factor
    story.append(d)
    story.append(Spacer(1, 13))


def build():
    (OUT / "diagrams").mkdir(exist_ok=True)
    for name, fn in [
        ("architecture", architecture),
        ("ingestion", ingestion),
        ("deployment", deployment),
        ("data-model", data_model),
    ]:
        renderSVG.drawToFile(fn(), str(OUT / "diagrams" / f"{name}.svg"))
    title(
        "01",
        "HybridForge RAG",
        "Architecture, implementation and production qualification | Version 1.0 | 16 October 2026",
    )
    story.append(Spacer(1, 30))
    p("Answers with<br/>an evidence trail.", "TitleHF")
    p(
        "A runnable hybrid retrieval system that combines lexical search and dense similarity, enforces tenant permissions, and returns structured answers with inspectable source citations."
    )
    diagram(data_model())
    table(
        ["DELIVERED", "QUALIFICATION"],
        [
            [
                "Source, API and browser workbench",
                "38 automated tests passed; 3 PostgreSQL tests skipped",
            ],
            [
                "Real-provider and database adapters",
                "Paid model calls and production database behavior not executed here",
            ],
            [
                "Diagrams, runbooks and deployment templates",
                "Not deployed; production acceptance remains open",
            ],
        ],
        [246, 247],
    )
    p(
        "Prepared as an engineering project and review package. Local evidence supports the verified features only; it is not a production certification.",
        "SmallHF",
    )

    title(
        "02",
        "System at a glance",
        "Read the Markdown documents for detailed contracts, decisions and operational procedures.",
    )
    table(
        ["AREA", "WHAT IS IMPLEMENTED"],
        [
            [
                "Retrieval",
                "PostgreSQL full-text + exact pgvector search, RRF fusion and optional reranker adapter",
            ],
            [
                "Data lifecycle",
                "Document fingerprints, optimistic version checks, atomic replace and cascading delete",
            ],
            [
                "Security",
                "OIDC RS256 verifier, scopes, group ACLs, forced database row-level security",
            ],
            [
                "Generation",
                "Real embedding/chat API adapter, structured claims, source-ID and quote validation",
            ],
            [
                "Experience",
                "Same-origin browser workbench, evidence explorer, source versions and diagnostic modes",
            ],
            [
                "Operations",
                "Input bounds, local admission controls, Prometheus metrics and optional OTLP traces",
            ],
        ],
        [110, 383],
    )
    heading("Two deliberately different modes")
    p(
        "<b>Offline demo:</b> SQLite, Python BM25, deterministic hash vectors and evidence extraction. Runs without model credentials. Hash vectors do not provide learned semantic search."
    )
    p(
        "<b>Production adapter:</b> PostgreSQL/pgvector, real embeddings and structured model generation. Requires verified identity, database configuration, provider credentials and deployment qualification."
    )
    heading("Guide map")
    p(
        "03 architecture; 04 retrieval mechanics; 05 ingestion; 06 security; 07 deployment; 08 API; 09 evaluation; 10 operations; 11 release gates; 12 decisions and references."
    )

    title(
        "03",
        "Architecture",
        "Policy scope is established before evidence can reach rank fusion or the model.",
    )
    diagram(architecture())
    p(
        "Lexical and dense SQL searches share one repeatable-read transaction. Generation occurs after the transaction, using the selected evidence snapshot. Permission changes after retrieval do not recall evidence already in flight.",
        "SmallHF",
    )

    title(
        "04",
        "How hybrid retrieval works",
        "Separate retrieval signals; one traceable, bounded evidence set.",
    )
    table(
        ["STAGE", "MECHANISM", "WHY IT MATTERS"],
        [
            [
                "Lexical",
                "tsvector, GIN and ts_rank_cd",
                "Handles exact identifiers and vocabulary matches",
            ],
            [
                "Dense",
                "1 minus cosine distance",
                "Finds learned conceptual similarity in real-provider mode",
            ],
            [
                "Fusion",
                "Sum of 1 / (60 + rank)",
                "Combines different ranking scales without adding raw scores",
            ],
            [
                "Reranking",
                "Optional cross-encoder",
                "Reorders fused candidates using query-passage relevance",
            ],
            [
                "Selection",
                "Overlap suppression and character budget",
                "Avoids wasting context on duplicate passages",
            ],
            [
                "Generation",
                "Structured claims with exact quotes",
                "Produces a provenance-checkable response contract",
            ],
        ],
        [88, 180, 225],
    )
    heading("A concrete fusion example")
    p(
        "If chunk A ranks first lexically and fourth semantically, its fused score is 1/61 + 1/64 = 0.03202. A chunk seen only at dense rank one scores 1/61 = 0.01639. These values rank evidence; they are not probabilities that an answer is correct."
    )
    heading("Intentional v1 limits")
    p(
        "The PostgreSQL dense branch performs an exact scan over the authorized subset. This establishes a correctness baseline but needs a measured corpus limit. Simply creating HNSW will not accelerate the current materialized-subset query."
    )
    p(
        "PostgreSQL full-text ranking is not BM25. Long natural-language queries may be too restrictive under websearch_to_tsquery; evaluate normalization or an alternate lexical backend against your data."
    )
    p(
        "Default bounds: 30 candidates per branch, at most 100; top_k defaults to 5 and is capped at 12; evidence budget is 16,000 characters. A 0.25 dense threshold is a starting parameter, not a calibrated confidence threshold."
    )

    title(
        "05",
        "Ingestion without partial updates",
        "Create, retry, replace and delete have explicit transactional semantics.",
    )
    diagram(ingestion())
    p(
        "The API accepts text/Markdown in JSON. It does not crawl URLs, parse PDFs or execute external connectors. A durable ingestion queue is an extension for workloads beyond the bounded synchronous path.",
        "SmallHF",
    )

    title(
        "06",
        "Security and answer trust",
        "Protect the evidence path first; treat generated claims as untrusted output.",
    )
    table(
        ["BOUNDARY", "CONTROL", "REMAINING RESPONSIBILITY"],
        [
            [
                "Identity",
                "RS256, issuer, audience, expiry and required claims",
                "Correct claim issuance and short token lifetime",
            ],
            [
                "Tenant / ACL",
                "Forced RLS plus explicit tenant filters",
                "Trusted service credentials and least-privilege networking",
            ],
            [
                "Model input",
                "Only selected authorized chunks",
                "Provider retention, region and approved data handling",
            ],
            [
                "Model output",
                "Known chunk IDs and exact quote membership",
                "Semantic entailment and source truth evaluation",
            ],
            [
                "Browser",
                "textContent rendering and self-only CSP",
                "Review future rich-text or link features",
            ],
            [
                "Resource use",
                "Body, context, candidate and concurrency bounds",
                "Gateway deadlines and fleet-wide quotas",
            ],
        ],
        [95, 192, 206],
    )
    heading("A valid quote is not proof of a valid claim")
    p(
        "The validator rejects an invented source ID or a quote that is absent from its cited chunk. It cannot prove that a claim follows from a valid quote. A malicious or mistaken document can still produce misleading output. Add independent answer-quality review and adversarial testing before deployment."
    )
    heading("Permission and deletion semantics")
    p(
        "Empty ACL means tenant-wide reading. Writer scope grants tenant administration. Token group changes take effect when new tokens are issued; in-flight requests use a retrieval snapshot. Deletion removes active rows, not already returned answers, backups or provider-retained copies."
    )
    p(
        "RLS uses transaction-local context. A compromised service database credential remains a serious breach: trusted application code can set the policy context. RLS is defense in depth, not a sandbox for arbitrary SQL access.",
        "SmallHF",
    )

    title(
        "07",
        "Deployment topology",
        "Separate application behavior from the infrastructure required to operate it.",
    )
    diagram(deployment())
    p(
        "Kubernetes templates include two replicas, readiness/liveness probes, resource limits, a disruption budget, nonroot execution and an example network policy. Operators must customize and validate them in their own cluster.",
        "SmallHF",
    )

    title(
        "08",
        "API and integration contract",
        "All content endpoints use a verified bearer principal; the body cannot choose a tenant.",
    )
    table(
        ["ENDPOINT", "SCOPE", "RESULT"],
        [
            ["PUT /v1/documents", "rag:write", "Create or replace with expected_version"],
            ["GET /v1/documents", "rag:read", "Visible metadata; PostgreSQL list capped at 1,000"],
            ["DELETE /v1/documents/{id}", "rag:write", "Delete matching version and its chunks"],
            ["POST /v1/search", "rag:read", "Selected evidence and rank diagnostics"],
            ["POST /v1/query", "rag:read", "Cited claims or explicit abstention"],
            ["GET /metrics", "rag:observe", "Per-process Prometheus metrics"],
            ["GET /health/ready", "Public", "Database readiness; no provider probe"],
        ],
        [185, 75, 233],
    )
    heading("Document preconditions")
    p(
        "Create with expected_version=0. For changed content, use the current version. Repeated identical fields are idempotent and preserve that version. A stale changed update returns 409. Text is limited to 100,000 characters, the full body to 700,000 bytes and generated chunks to 128."
    )
    heading("Errors and retries")
    p(
        "401/403 require valid credentials or permissions; 409 requires refreshing the document version; 413/422 require payload changes. Retry 429/502/503 with bounded backoff. Provider retries may incur additional charges. Invalid citations reject the whole generated answer rather than silently returning a partial result."
    )
    p(
        "The answer contains document ID, revision, source label, exact quote and chunk character range. Character offsets identify the full chunk, not just the quoted substring. See docs/API.md and docs/openapi.json.",
        "SmallHF",
    )

    title(
        "09",
        "Evaluation and evidence",
        "Measure retrieval, authorization and generation independently.",
    )
    results = json.loads((ROOT / "evals/results.json").read_text())["results"]
    rows = []
    for name, data in results.items():
        a = data["aggregate"]
        rows.append([name, f"{a['recall_at_k']:.2f}", f"{a['mrr']:.2f}", f"{a['ndcg_at_k']:.2f}"])
    table(["OFFLINE MODE", "RECALL@5", "MRR", "nDCG@5"], rows, [190, 101, 101, 101])
    p(
        "Actual local run: ten synthetic questions against six fictional documents. Dense mode uses hash vectors, not semantic embeddings. This result demonstrates the wiring and lexical recovery; it does not establish that hybrid outperforms a real semantic model.",
        "SmallHF",
    )
    heading("Verified test evidence")
    p(
        "38 automated tests passed and three PostgreSQL integration tests skipped. Coverage across the Python package was 84%, including unexecuted database/reranker/telemetry paths. A Python wheel was built successfully. Detailed evidence and environment limits are in docs/VALIDATION.md."
    )
    heading("Production evaluation plan")
    p(
        "Use a held-out corpus with exact codes, paraphrases, ambiguous questions, multi-document answers, unanswerable queries, conflicting revisions and injected instructions. Split by source family and time. Compare lexical, dense, hybrid and reranked hybrid under the same ACLs and budgets."
    )
    p(
        "Require zero unauthorized chunks. Measure answer faithfulness, completeness, refusal quality, quote correctness and semantic entailment separately. Qualify p50/p95/p99 latency, failure recovery and cost at the target tenant/corpus scale. A small synthetic recall score is not a production quality gate."
    )

    title(
        "10",
        "Operate, observe, recover",
        "Release and incident workflows are part of the engineering deliverable.",
    )
    heading("Deployment sequence")
    p(
        "Provision PostgreSQL and backups; run the migration with a separate owner identity; configure rag_app, OIDC and model credentials; deploy a scanned image behind TLS; verify isolation and real-provider smoke tests; then canary and expand after acceptance gates pass."
    )
    heading("Observability")
    p(
        "Prometheus tracks operation counts by bounded outcome labels and duration histograms. Optional OTLP spans cover embedding, storage, retrieval, reranking and generation. Application logs contain operation, outcome and request ID; source text, prompts and credentials are excluded. Protect metrics with rag:observe and network controls."
    )
    table(
        ["SYMPTOM", "FIRST RESPONSE"],
        [
            [
                "401 / 403 spike",
                "Inspect issuer, audience, scopes, group mapping and JWKS rotation; never disable validation",
            ],
            [
                "502 provider failures",
                "Check quota, availability and structured-output compatibility; preserve fail-closed behavior",
            ],
            [
                "Slow queries / 503",
                "Check admission limits, pool capacity, authorized corpus size and provider latency",
            ],
            [
                "Empty evidence",
                "Check tenant/ACLs, model identity, ingestion completeness and lexical semantics",
            ],
            [
                "Suspected disclosure",
                "Stop exposure, revoke credentials and preserve restricted incident evidence",
            ],
        ],
        [155, 338],
    )
    heading("Recovery and cost")
    p(
        "Use encrypted backups with WAL archiving and perform isolated restore drills. Verify schema, extension, role grants, forced RLS and tenant-negative tests after restoration. Budget embedding overlap, reingestion and retries. Global cost controls and hard workflow deadlines are not implemented."
    )

    title(
        "11",
        "Production acceptance gates",
        "Current status: runnable reference implementation, not production-certified.",
    )
    table(
        ["GATE", "REQUIRED EVIDENCE"],
        [
            [
                "Database correctness",
                "Execute all PostgreSQL integration and RLS tests using the actual non-owner role",
            ],
            [
                "Live provider compatibility",
                "Verify embeddings, structured generation, real JWKS and key rotation",
            ],
            [
                "Quality and safety",
                "Held-out retrieval metrics, expert answer review and injection/entailment tests",
            ],
            [
                "Capacity and resilience",
                "Load/soak results, service limits, provider outage drills and DB recovery",
            ],
            [
                "Supply chain",
                "Image build/scan, SBOM, dependency review, base-image/action/model pins",
            ],
            [
                "Infrastructure",
                "TLS and CA validation, secret rotation, alert delivery and backup restore",
            ],
            ["Release process", "Staging acceptance, canary, rollback rehearsal and named owners"],
        ],
        [155, 338],
    )
    heading("Explicitly outside the implemented scope")
    p(
        "PDF/OCR ingestion, crawlers, external source connectors, durable asynchronous ingestion, immutable revision storage, conversation memory, answer caching, distributed rate limits and ANN query execution are not implemented. Add them only with the corresponding authorization, retention and failure semantics."
    )
    p(
        "The optional cross-encoder adapter exists but was not executed here. Docker, Kubernetes, hosted database operation and paid model calls remain unverified. Do not present the deployment templates or local smoke scores as evidence of production scale."
    )

    title(
        "12",
        "Decisions and primary references",
        "Trace design choices to documentation and retain an auditable qualification record.",
    )
    table(
        ["DECISION", "RATIONALE"],
        [
            [
                "Single PostgreSQL store",
                "Keep ACL, document and retrieval representations transactional",
            ],
            ["RRF ranking", "Avoid mixing uncalibrated raw lexical and vector scores"],
            [
                "Exact authorized dense scan",
                "Establish a clear permission-aware retrieval baseline",
            ],
            ["Structured claims + quotes", "Make source provenance deterministically checkable"],
            [
                "Explicit offline mode",
                "Allow no-key demos without pretending hash vectors are semantic",
            ],
            [
                "No cache or memory in v1",
                "Avoid stale entitlement and conversation-retention complexity",
            ],
        ],
        [170, 323],
    )
    heading("Primary technical references")
    refs = [
        ("pgvector", "https://github.com/pgvector/pgvector"),
        ("PostgreSQL row security", "https://www.postgresql.org/docs/current/ddl-rowsecurity.html"),
        (
            "PostgreSQL full-text search",
            "https://www.postgresql.org/docs/current/textsearch-controls.html",
        ),
        ("OpenAI embeddings guide", "https://developers.openai.com/api/docs/guides/embeddings"),
    ]
    for name, url in refs:
        p(f'<b>{name}</b><br/><link href="{url}" color="#087f83">{url}</link>', "SmallHF")
    heading("Document set")
    p(
        "The project includes ARCHITECTURE, API, SECURITY, OPERATIONS, EVALUATION, DECISIONS, PRODUCTION_READINESS, VALIDATION and REFERENCES Markdown documents; editable Mermaid and SVG diagrams; API schema; dependency locks; test reports; and deployment configuration. Consult those files for full implementation details.",
        "SmallHF",
    )
    doc = SimpleDocTemplate(
        str(OUT / "HybridForge_Architecture_Handbook.pdf"),
        pagesize=(595.28, 841.89),
        rightMargin=51,
        leftMargin=51,
        topMargin=49,
        bottomMargin=49,
        title="HybridForge RAG - Architecture and Engineering Handbook",
        author="HybridForge Engineering",
        subject="Hybrid retrieval implementation and qualification",
    )

    def footer(c, doc):
        c.setStrokeColor(LINE)
        c.line(51, 38, 544, 38)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(51, 25, "HYBRIDFORGE RAG  /  ENGINEERING REFERENCE  /  2026-10-16")
        c.drawRightString(544, 25, str(doc.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUT / "HybridForge_Architecture_Handbook.pdf")


if __name__ == "__main__":
    build()
