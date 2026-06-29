"""
OpenTelemetry bootstrap — call configure_otel(service_name) once at process
startup (main.py for the API, worker.py for the Temporal worker).

Sets up three OTel providers and exports everything via OTLP gRPC to the
OpenTelemetry Collector, which fans out to Prometheus (metrics) and
Grafana Tempo (traces).
"""

import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from config import settings

_configured = False


def configure_otel(service_name: str) -> None:
    """
    Initialize TracerProvider, MeterProvider, and LoggerProvider.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: service_name,
            ResourceAttributes.SERVICE_VERSION: settings.app_version,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: settings.environment,
        }
    )

    endpoint = settings.otel_endpoint

    # ── Traces ────────────────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics ───────────────────────────────────────────────────────────────
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=15_000,  # matches Prometheus scrape interval
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ── Logs ──────────────────────────────────────────────────────────────────
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)

    logging.getLogger(__name__).info(
        "[otel] configured for service=%s endpoint=%s env=%s version=%s",
        service_name,
        endpoint,
        settings.environment,
        settings.app_version,
    )
