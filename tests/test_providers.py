import json

import httpx
import pytest

from hybridforge.config import Settings
from hybridforge.models import Hit, ProviderError
from hybridforge.providers import OpenAIProvider


def provider(handler):
    client = httpx.Client(
        base_url="https://provider.example/v1/", transport=httpx.MockTransport(handler)
    )
    return OpenAIProvider(Settings(), client=client)


def test_embedding_payload_and_order():
    def handle(request):
        body = json.loads(request.content)
        assert body["dimensions"] == 1536
        assert body["model"] == "text-embedding-3-small"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2.0] * 1536},
                    {"index": 0, "embedding": [1.0] * 1536},
                ]
            },
        )

    p = provider(handle)
    assert p.embed(["a", "b"])[0][0] == 1
    p.close()


@pytest.mark.parametrize(
    "data", [[{"index": 0, "embedding": [1]}], [{"index": 0, "embedding": [0.0] * 1536}], []]
)
def test_invalid_embeddings_fail(data):
    p = provider(lambda _: httpx.Response(200, json={"data": data}))
    with pytest.raises(ProviderError):
        p.embed(["a"])
    p.close()


def test_provider_retries_transient_error(monkeypatch):
    monkeypatch.setattr("hybridforge.providers.time.sleep", lambda _: None)
    calls = []

    def handler(_):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 1536}]})

    p = provider(handler)
    assert p.embed(["a"])
    assert len(calls) == 3
    p.close()


def test_non_retryable_errors_do_not_leak_body():
    p = provider(lambda _: httpx.Response(401, text="secret-provider-response"))
    with pytest.raises(ProviderError) as error:
        p.embed(["a"])
    assert "secret-provider-response" not in str(error.value)
    p.close()


def test_structured_generation_request():
    h = Hit("chunk", "doc", 1, "Title", "source", "Restart the editor once.", 0, 24)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["messages"][0]["role"] == "system"
        evidence = json.loads(payload["messages"][1]["content"])
        assert evidence["evidence"][0]["chunk_id"] == "chunk"
        answer = {"claims": [{"text": "Restart once.", "chunk_id": "chunk", "quote": h.text}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    p = provider(handler)
    assert p.generate("How to recover?", [h]).claims[0].quote == h.text
    p.close()
