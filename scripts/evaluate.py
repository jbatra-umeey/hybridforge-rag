"""Offline retrieval regression suite, or evaluate a deployed real-provider API."""

import argparse
import json
import math
import os
import statistics
import tempfile
from pathlib import Path

import httpx

from hybridforge.config import Settings
from hybridforge.models import DocumentInput, Principal, QueryInput
from hybridforge.providers import DemoProvider
from hybridforge.service import RAGService
from hybridforge.storage import SQLiteStore


def measures(retrieved, relevant, k):
    # Collapse duplicate chunks to documents before calculating document-level metrics.
    documents = list(dict.fromkeys(retrieved))[:k]
    matched = set(documents).intersection(relevant)
    recall = len(matched) / len(relevant)
    mrr = next((1 / (i + 1) for i, d in enumerate(documents) if d in relevant), 0)
    dcg = sum(1 / math.log2(i + 2) for i, d in enumerate(documents) if d in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return {"recall_at_k": recall, "mrr": mrr, "ndcg_at_k": dcg / ideal}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", help="Use an already seeded API and RAG_TOKEN")
    parser.add_argument("--output", default="evals/results.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "evals/questions.json").read_text())
    p = Principal("demo", "evaluator", ("engineering",), frozenset({"rag:read", "rag:write"}))
    results = {}
    with tempfile.TemporaryDirectory() as tmp, httpx.Client(timeout=300) as client:
        service = RAGService(SQLiteStore(str(Path(tmp) / "demo.db")), DemoProvider(), Settings())
        if not args.api_url:
            for d in json.loads((root / "examples/documents.json").read_text()):
                service.ingest(p, DocumentInput(**d))
        for mode in ["lexical", "dense", "hybrid"]:
            rows = []
            for case in cases:
                query = QueryInput(question=case["question"], mode=mode)
                if args.api_url:
                    response = client.post(
                        args.api_url.rstrip("/") + "/v1/search",
                        json=query.model_dump(),
                        headers={"Authorization": "Bearer " + os.environ["RAG_TOKEN"]},
                    )
                    response.raise_for_status()
                    data = response.json()
                    docs = [h["document_id"] for h in data["evidence"]]
                    latency = data["diagnostics"]["retrieval_ms"]
                else:
                    hits, diag = service.retrieve(p, query)
                    docs, latency = [h.document_id for h in hits], diag["retrieval_ms"]
                rows.append(
                    {
                        "question": case["question"],
                        "retrieved": docs,
                        **measures(docs, case["relevant"], 5),
                        "retrieval_ms": latency,
                    }
                )
            results[mode] = {
                "aggregate": {
                    key: statistics.mean(r[key] for r in rows)
                    for key in ["recall_at_k", "mrr", "ndcg_at_k", "retrieval_ms"]
                },
                "cases": rows,
            }
        service.store.close()
    report = {
        "dataset": "10 synthetic document-level smoke cases; not a production benchmark",
        "mode": "live_api" if args.api_url else "offline_hash_demo",
        "results": results,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v["aggregate"] for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
