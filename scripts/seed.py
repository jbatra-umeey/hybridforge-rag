"""Seed fictional examples through the API; safe to rerun unchanged content."""

import json
import os
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
token = os.environ.get("RAG_TOKEN") or os.environ.get("DEMO_TOKEN")
if not token:
    raise SystemExit("Set RAG_TOKEN or DEMO_TOKEN")
with httpx.Client(
    base_url=os.getenv("RAG_URL", "http://127.0.0.1:8000"),
    headers={"Authorization": f"Bearer {token}"},
    timeout=300,
) as client:
    for document in json.loads((root / "examples/documents.json").read_text()):
        response = client.put("/v1/documents", json=document)
        response.raise_for_status()
        print(json.dumps(response.json()))
