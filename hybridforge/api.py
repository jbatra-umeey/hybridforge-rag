import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Settings
from .models import Conflict, DocumentInput, ProviderError, QueryInput
from .observability import Metrics, configure_tracing, log, safe_span
from .providers import CrossEncoderReranker, DemoProvider, OpenAIProvider
from .security import Authenticator, RateLimiter
from .service import RAGService
from .storage import PostgresStore, SQLiteStore


class BodyLimitMiddleware:
    """Reject oversized streaming bodies before FastAPI parses them."""

    def __init__(self, app, max_bytes=700_000):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data.extend(message.get("body", b""))
            if len(data) > self.max_bytes:
                response = JSONResponse({"detail": "Request body exceeds limit"}, status_code=413)
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def create_app(settings=None, store=None, provider=None):
    settings = settings or Settings.from_env()
    settings.validate()
    metrics = Metrics()
    auth, limiter = Authenticator(settings), RateLimiter(settings.rpm)
    semaphore = threading.BoundedSemaphore(settings.max_inflight)

    @asynccontextmanager
    async def lifespan(app):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        trace_provider = configure_tracing()
        actual_store = store or (
            SQLiteStore(settings.sqlite_path)
            if settings.mode == "demo"
            else PostgresStore(settings.database_url)
        )
        actual_provider = provider or (
            DemoProvider() if settings.mode == "demo" else OpenAIProvider(settings)
        )
        reranker = (
            CrossEncoderReranker(settings.reranker_model)
            if settings.reranker == "cross_encoder"
            else None
        )
        app.state.service = RAGService(actual_store, actual_provider, settings, reranker)
        try:
            yield
        finally:
            actual_store.close()
            actual_provider.close()
            if trace_provider:
                trace_provider.shutdown()

    app = FastAPI(
        title="HybridForge RAG",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        description="Tenant-aware lexical + dense retrieval with verifiable evidence.",
    )
    app.state.auth = auth
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def principal(authorization: str | None = Header(default=None)):
        p = auth.authenticate(authorization)
        limiter.check(p)
        return p

    def reader(p=Depends(principal)):
        if "rag:read" not in p.scopes:
            raise HTTPException(403, "rag:read scope required")
        return p

    def writer(p=Depends(principal)):
        if not p.can_write:
            raise HTTPException(403, "rag:write scope required")
        return p

    @contextmanager
    def operation(name, request):
        if not semaphore.acquire(blocking=False):
            raise HTTPException(503, "Service at capacity", headers={"Retry-After": "2"})
        outcome = "success"
        try:
            with metrics.duration.labels(name).time(), safe_span("rag." + name) as span:
                span.set_attribute("request.id", request.state.request_id)
                yield
        except Conflict as exc:
            outcome = "conflict"
            raise HTTPException(409, str(exc)) from exc
        except ProviderError as exc:
            outcome = "provider_error"
            raise HTTPException(502, "Model request failed; retry later") from exc
        except ValueError as exc:
            outcome = "invalid"
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            outcome = "error"
            # Never record provider response, question, token, DSN or document text.
            raise HTTPException(503, "Operation unavailable; retry later") from exc
        finally:
            metrics.requests.labels(name, outcome).inc()
            log.info(
                json.dumps(
                    {
                        "event": "rag_operation",
                        "operation": name,
                        "outcome": outcome,
                        "request_id": request.state.request_id,
                    }
                )
            )
            semaphore.release()

    @app.get("/health/live", tags=["Operations"])
    def live():
        return {"status": "alive", "mode": settings.mode}

    @app.get("/health/ready", tags=["Operations"])
    def ready():
        try:
            app.state.service.store.ready()
        except Exception as exc:
            raise HTTPException(503, "Storage not ready") from exc
        return {"status": "ready", "provider_connectivity": "not_probed"}

    @app.get("/metrics", tags=["Operations"])
    def prometheus(p=Depends(principal)):
        if "rag:observe" not in p.scopes:
            raise HTTPException(403, "rag:observe scope required")
        return Response(content=generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.put("/v1/documents", tags=["Documents"])
    def upsert(document: DocumentInput, request: Request, p=Depends(writer)):
        with operation("ingest", request):
            return app.state.service.ingest(p, document)

    @app.get("/v1/documents", tags=["Documents"])
    def documents(request: Request, p=Depends(reader)):
        with operation("list", request):
            return {"documents": app.state.service.store.list_documents(p)}

    @app.delete("/v1/documents/{document_id}", status_code=204, tags=["Documents"])
    def delete(
        document_id: str, request: Request, expected_version: int = Query(ge=1), p=Depends(writer)
    ):
        with operation("delete", request):
            app.state.service.store.delete(p, document_id, expected_version)
        return Response(status_code=204)

    @app.post("/v1/search", tags=["Retrieval"])
    def search(query: QueryInput, request: Request, p=Depends(reader)):
        with operation("search", request):
            hits, diagnostics = app.state.service.retrieve(p, query)
            return {"evidence": [asdict(h) for h in hits], "diagnostics": diagnostics}

    @app.post("/v1/query", tags=["Retrieval"])
    def query(query: QueryInput, request: Request, p=Depends(reader)):
        with operation("query", request):
            result = app.state.service.query(p, query)
            result["request_id"] = request.state.request_id
            return result

    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(static / "index.html")

    return app
