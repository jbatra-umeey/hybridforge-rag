"""Run against a freshly migrated test database using the non-owner rag_app role."""

import os
import uuid
from dataclasses import replace

import pytest

from hybridforge.models import Conflict, Principal, QueryInput
from hybridforge.providers import DemoProvider
from hybridforge.service import RAGService
from hybridforge.storage import PostgresStore

pytestmark = pytest.mark.postgres


class TestVectorProvider(DemoProvider):
    embedding_id = "integration-hash-v1:1536"

    def embed(self, texts):
        return [v + [0.0] * 1280 for v in super().embed(texts)]


@pytest.fixture
def pg(settings):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    store = PostgresStore(url)
    p = Principal(
        "test-" + uuid.uuid4().hex, "integration", (), frozenset({"rag:read", "rag:write"})
    )
    service = RAGService(store, TestVectorProvider(), settings)
    yield service, p
    for doc in store.list_documents(p):
        store.delete(p, doc["document_id"], doc["version"])
    store.close()


def test_postgres_hybrid_lifecycle(pg, document):
    service, p = pg
    service.ingest(p, document)
    answer = service.query(p, QueryInput(question="ERR_BRIDGE_042"))
    assert answer["status"] == "answered"
    assert answer["diagnostics"]["lexical_candidates"] > 0
    assert answer["diagnostics"]["dense_candidates"] > 0
    assert service.ingest(p, document)["changed"] is False
    with pytest.raises(Conflict):
        service.ingest(p, document.model_copy(update={"text": "Changed text."}))
    service.store.delete(p, document.document_id, 1)
    assert not service.retrieve(p, QueryInput(question="ERR_BRIDGE_042"))[0]


def test_postgres_database_rls_and_pool_reset(pg, document):
    service, p = pg
    service.ingest(p, document)
    other = replace(p, tenant="wrong-tenant")
    with service.store.transaction(other) as db:
        assert db.execute("SELECT * FROM chunks").fetchall() == []
        assert db.execute("SELECT * FROM documents").fetchall() == []
    with service.store.pool.connection() as db:
        assert db.execute("SELECT * FROM chunks").fetchall() == []
    assert not service.retrieve(other, QueryInput(question="ERR_BRIDGE_042"))[0]


def test_postgres_acl_and_wrong_tenant_insert(pg, document):
    service, p = pg
    service.ingest(p, document.model_copy(update={"acl_groups": ["executive"]}))
    reader = replace(p, scopes=frozenset({"rag:read"}))
    assert not service.retrieve(reader, QueryInput(question="ERR_BRIDGE_042"))[0]
    assert service.retrieve(
        replace(reader, groups=("executive",)), QueryInput(question="ERR_BRIDGE_042")
    )[0]
    import psycopg

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with service.store.transaction(p) as db:
            db.execute("""INSERT INTO documents(tenant,document_id,version,digest,title,source,embedding_id)
                       VALUES('forbidden','doc',1,'hash','Title','source','test')""")
