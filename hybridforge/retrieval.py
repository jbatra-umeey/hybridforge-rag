"""Pure retrieval functions. Scores across engines are fused by rank, never added raw."""

import hashlib
import math
import re
from collections import Counter
from dataclasses import replace

from .models import Hit


def tokens(text):
    return re.findall(r"[\w-]+", text.lower())


def chunk_text(text, size=1200, overlap=180):
    if not 0 <= overlap < size:
        raise ValueError("overlap must be smaller than size")
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + size // 2, end), text.rfind(" ", start + size // 2, end)
            )
            if boundary > start:
                end = boundary
        if text[start:end].strip():
            result.append((start, end, text[start:end]))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return result


def fingerprint(doc, embedding_id):
    import json

    payload = {k: v for k, v in doc.model_dump().items() if k != "expected_version"}
    payload["embedding_id"] = embedding_id
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def make_chunks(doc, digest):
    return [
        Hit(
            hashlib.sha256(f"{doc.document_id}:{digest}:{start}".encode()).hexdigest(),
            doc.document_id,
            0,
            doc.title,
            doc.source,
            text,
            start,
            end,
        )
        for start, end, text in chunk_text(doc.text)
    ]


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("Embedding dimension mismatch")
    denom = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / denom if denom else 0.0


def bm25(query, hits):
    """Offline reference BM25 computed only over the authorized corpus."""
    corpus = [tokens(h.title + " " + h.text) for h in hits]
    avg = sum(map(len, corpus)) / max(1, len(corpus))
    scores = [0.0] * len(hits)
    for term in set(tokens(query)):
        df = sum(term in words for words in corpus)
        idf = math.log(1 + (len(corpus) - df + 0.5) / (df + 0.5))
        for i, words in enumerate(corpus):
            tf = Counter(words)[term]
            if tf:
                scores[i] += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(words) / avg))
    return sorted(
        [replace(h, score=s) for h, s in zip(hits, scores) if s > 0],
        key=lambda h: (-h.score, h.chunk_id),
    )


def rrf(lexical, dense, k=60):
    fused = {}
    for name, hits in [("lexical", lexical), ("dense", dense)]:
        seen = set()
        for rank, hit in enumerate(hits, 1):
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            if hit.chunk_id not in fused:
                fused[hit.chunk_id] = replace(hit, score=0.0, ranks={})
            fused[hit.chunk_id].score += 1 / (k + rank)
            fused[hit.chunk_id].ranks[name] = rank
    return sorted(fused.values(), key=lambda h: (-h.score, h.chunk_id))


def select_context(hits, top_k, char_budget):
    selected, used, intervals = [], 0, {}
    for hit in hits:
        ranges = intervals.setdefault(hit.document_id, [])
        if any(
            max(0, min(hit.end, end) - max(hit.start, start)) / max(1, hit.end - hit.start) > 0.5
            for start, end in ranges
        ):
            continue
        if used + len(hit.text) > char_budget:
            continue
        selected.append(hit)
        used += len(hit.text)
        ranges.append((hit.start, hit.end))
        if len(selected) == top_k:
            break
    return selected
