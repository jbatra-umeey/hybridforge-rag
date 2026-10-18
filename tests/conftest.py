import pytest

from hybridforge.config import Settings
from hybridforge.models import DocumentInput, Principal
from hybridforge.providers import DemoProvider
from hybridforge.service import RAGService
from hybridforge.storage import SQLiteStore


@pytest.fixture
def settings(tmp_path):
    return Settings(
        sqlite_path=str(tmp_path / "rag.db"), demo_token="test-token-long-enough", rpm=1000
    )


@pytest.fixture
def writer():
    return Principal("acme", "writer", ("engineering",), frozenset({"rag:read", "rag:write"}))


@pytest.fixture
def reader():
    return Principal("acme", "reader", ("engineering",))


@pytest.fixture
def document():
    return DocumentInput(
        document_id="runbook",
        title="Bridge recovery",
        text="ERR_BRIDGE_042 indicates a bridge handshake timeout. Restart the editor once.",
    )


@pytest.fixture
def service(settings):
    return RAGService(SQLiteStore(settings.sqlite_path), DemoProvider(), settings)
