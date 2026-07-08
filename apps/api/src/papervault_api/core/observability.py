from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from papervault_api.core.config import Settings


def configure_observability(app: FastAPI, settings: Settings) -> None:
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app)

    if not settings.otel_exporter_otlp_endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)),
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
