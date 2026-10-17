import time
from dataclasses import asdict

from .models import ProviderError
from .observability import safe_span
from .retrieval import fingerprint, make_chunks, rrf, select_context


class RAGService:
    def __init__(self, store, provider, settings, reranker=None):
        self.store, self.provider, self.settings, self.reranker = (
            store,
            provider,
            settings,
            reranker,
        )

    def ingest(self, principal, document):
        if not principal.can_write:
            raise PermissionError("Writer scope required")
        digest = fingerprint(document, self.provider.embedding_id)
        chunks = make_chunks(document, digest)
        if len(chunks) > 128:
            raise ValueError("Document produces too many chunks; split it into smaller documents")
        with safe_span("rag.embed.document"):
            vectors = self.provider.embed([h.title + "\n" + h.text for h in chunks])
        # Embedding failure cannot partially replace the previous document.
        with safe_span("rag.store.commit"):
            return self.store.upsert(
                principal, document, digest, chunks, vectors, self.provider.embedding_id
            )

    def retrieve(self, principal, query):
        start = time.perf_counter()
        with safe_span("rag.embed.query"):
            vector = self.provider.embed([query.question])[0]
        with safe_span("rag.search.authorized"):
            lexical, dense = self.store.search(
                principal,
                query.question,
                vector,
                self.provider.embedding_id,
                query.candidate_k,
                self.settings.min_dense_score,
            )
        # Diagnostic modes reuse the same snapshot. Both branches run for fair comparison.
        ranked = rrf(
            lexical if query.mode != "dense" else [], dense if query.mode != "lexical" else []
        )
        if self.reranker:
            with safe_span("rag.rerank"):
                ranked = self.reranker.rank(query.question, ranked[: query.candidate_k])
        selected = select_context(ranked, query.top_k, self.settings.context_chars)
        return selected, {
            "retrieval_ms": round((time.perf_counter() - start) * 1000, 2),
            "lexical_candidates": len(lexical),
            "dense_candidates": len(dense),
            "selected_chunks": len(selected),
            "embedding_id": self.provider.embedding_id,
            "retrieval_mode": query.mode,
            "reranker": self.settings.reranker,
        }

    def query(self, principal, query):
        hits, diagnostics = self.retrieve(principal, query)
        if not hits:
            return self.answer([], [], diagnostics, "no_evidence")
        with safe_span("rag.generate"):
            generated = self.provider.generate(query.question, hits)
        known = {h.chunk_id: h for h in hits}
        valid = []
        for claim in generated.claims:
            if claim.chunk_id not in known or claim.quote not in known[claim.chunk_id].text:
                # Never silently drop invalid claims and leave a misleading partial answer.
                raise ProviderError("Generated answer failed citation validation")
            valid.append(claim)
        return self.answer(valid, hits, diagnostics, "insufficient_evidence" if not valid else None)

    def answer(self, claims, hits, diagnostics, reason):
        by_id = {h.chunk_id: h for h in hits}
        citations = []
        for index, claim in enumerate(claims, 1):
            h = by_id[claim.chunk_id]
            citations.append(
                {
                    "number": index,
                    "chunk_id": h.chunk_id,
                    "document_id": h.document_id,
                    "version": h.version,
                    "title": h.title,
                    "source": h.source,
                    "quote": claim.quote,
                    "start_char": h.start,
                    "end_char": h.end,
                }
            )
        return {
            "status": "answered" if claims else "abstained",
            "reason": reason,
            "answer": "\n\n".join(f"{c.text} [{i}]" for i, c in enumerate(claims, 1)),
            "citations": citations,
            "evidence": [asdict(h) for h in hits],
            "diagnostics": diagnostics,
            "generation_mode": self.provider.mode,
            "citation_check": "source_and_exact_quote_only; semantic_entailment_not_verified",
        }
