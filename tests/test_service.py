from concurrent.futures import ThreadPoolExecutor

import pytest

from hybridforge.models import (
    Conflict,
    EvidenceClaim,
    GeneratedAnswer,
    Principal,
    ProviderError,
    QueryInput,
)


def test_ingest_retrieve_cite_delete(service, writer, reader, document):
    result = service.ingest(writer, document)
    assert result["version"] == 1
    answer = service.query(reader, QueryInput(question="ERR_BRIDGE_042"))
    assert answer["status"] == "answered"
    assert answer["citations"][0]["quote"] in document.text
    assert answer["citations"][0]["version"] == 1
    service.store.delete(writer, document.document_id, 1)
    assert service.query(reader, QueryInput(question="ERR_BRIDGE_042"))["status"] == "abstained"


def test_tenant_isolation_before_retrieval(service, writer, document):
    service.ingest(writer, document)
    other = Principal("other", "reader")
    hits, _ = service.retrieve(other, QueryInput(question="ERR_BRIDGE_042"))
    assert not hits
    assert not service.store.list_documents(other)


def test_group_acl_and_immediate_revocation(service, writer, reader, document):
    service.ingest(writer, document)
    updated = document.model_copy(update={"acl_groups": ["executive"], "expected_version": 1})
    service.ingest(writer, updated)
    assert not service.retrieve(reader, QueryInput(question="ERR_BRIDGE_042"))[0]
    assert service.retrieve(
        Principal("acme", "exec", ("executive",)), QueryInput(question="ERR_BRIDGE_042")
    )[0]
    assert not service.store.list_documents(reader)


def test_idempotency_and_stale_update(service, writer, document):
    service.ingest(writer, document)
    assert service.ingest(writer, document)["changed"] is False
    with pytest.raises(Conflict):
        service.ingest(writer, document.model_copy(update={"text": "A changed document body."}))
    result = service.ingest(
        writer,
        document.model_copy(update={"text": "A changed document body.", "expected_version": 1}),
    )
    assert result["version"] == 2


def test_failed_embeddings_keep_previous_document(service, writer, reader, document, monkeypatch):
    service.ingest(writer, document)
    original = service.provider.embed

    def fail(_):
        raise ProviderError("Unavailable")

    monkeypatch.setattr(service.provider, "embed", fail)
    with pytest.raises(ProviderError):
        service.ingest(
            writer, document.model_copy(update={"text": "New body content.", "expected_version": 1})
        )
    monkeypatch.setattr(service.provider, "embed", original)
    assert (
        service.query(reader, QueryInput(question="ERR_BRIDGE_042"))["citations"][0]["version"] == 1
    )


@pytest.mark.parametrize(
    "chunk_id,quote", [("invented", "Invented source quote."), (None, "Invented source quote.")]
)
def test_invalid_citations_fail_closed(
    service, writer, reader, document, monkeypatch, chunk_id, quote
):
    service.ingest(writer, document)

    def bad_answer(q, hits):
        return GeneratedAnswer(
            claims=[
                EvidenceClaim(
                    text="Unsupported claim", quote=quote, chunk_id=chunk_id or hits[0].chunk_id
                )
            ]
        )

    monkeypatch.setattr(service.provider, "generate", bad_answer)
    with pytest.raises(ProviderError):
        service.query(reader, QueryInput(question="ERR_BRIDGE_042"))


def test_concurrent_updates_have_one_winner(service, writer, document):
    service.ingest(writer, document)

    def update(i):
        try:
            service.ingest(
                writer,
                document.model_copy(
                    update={"text": f"Changed document {i}.", "expected_version": 1}
                ),
            )
            return "ok"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(update, range(8)))
    assert results.count("ok") == 1
    assert results.count("conflict") == 7


def test_store_prevents_reader_write(service, reader, document):
    with pytest.raises(PermissionError):
        service.ingest(reader, document)
    with pytest.raises(PermissionError):
        service.store.delete(reader, "runbook", 1)


def test_no_evidence_never_calls_generator(service, reader, monkeypatch):
    def fail(*args):
        raise AssertionError("Should not generate")

    monkeypatch.setattr(service.provider, "generate", fail)
    assert service.query(reader, QueryInput(question="Unknown question"))["status"] == "abstained"
