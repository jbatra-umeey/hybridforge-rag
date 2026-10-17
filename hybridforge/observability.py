import logging

from opentelemetry import trace
from prometheus_client import CollectorRegistry, Counter, Histogram

log = logging.getLogger("hybridforge")


def configure_tracing():
    import os

    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "hybridforge-rag"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "rag_operations_total",
            "RAG operations",
            ["operation", "outcome"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "rag_operation_seconds",
            "RAG operation latency",
            ["operation"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 90),
            registry=self.registry,
        )


def safe_span(name):
    # Database exceptions can embed row contents: never export exception payloads.
    return trace.get_tracer("hybridforge").start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    )
