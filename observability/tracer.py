# observability/tracer.py
# ALL imports at the very top — no imports inside functions

import json
import logging
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,      # ← here, not inside if block
    ConsoleSpanExporter
)
from opentelemetry.sdk.resources import Resource
from config import settings

logger = logging.getLogger(__name__)


def setup_tracing() -> TracerProvider:
    resource = Resource.create({
        "service.name":    "it-helpdesk-agent",
        "service.version": "1.0.0"
    })

    provider = TracerProvider(resource=resource)

    if settings.otel_export == "file":
        # File exporter class defined here — no imports needed
        class FileSpanExporter:
            def export(self, spans):
                with open("data/traces.jsonl", "a") as f:
                    for span in spans:
                        f.write(json.dumps({
                            "name":        span.name,
                            "trace_id":    format(
                                span.context.trace_id, "032x"
                            ),
                            "duration_ms": round(
                                (span.end_time - span.start_time)
                                / 1_000_000, 2
                            ),
                            "attributes":  dict(span.attributes or {}),
                            "status":      span.status.status_code.name
                        }) + "\n")
                return 0

            def shutdown(self): pass
            def force_flush(self, timeout_millis=30000): pass

        # SimpleSpanProcessor now available — imported at top
        provider.add_span_processor(
            SimpleSpanProcessor(FileSpanExporter())
        )
        logger.info("OTEL → file: data/traces.jsonl")

    else:
        # SimpleSpanProcessor available here too
        provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )
        logger.info("OTEL → console")

    trace.set_tracer_provider(provider)
    return provider


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("it-helpdesk-agent")


@contextmanager
def span(name: str, attributes: dict = None):
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        try:
            yield s
        except Exception as e:
            s.record_exception(e)
            s.set_status(trace.StatusCode.ERROR, str(e))
            raise


def record_tool_span(
    tool_name: str,
    session_id: str,
    agent_name: str,
    duration_ms: float,
    success: bool,
    approval_required: bool = False
):
    tracer = get_tracer()
    with tracer.start_as_current_span(f"tool.{tool_name}") as s:
        s.set_attribute("tool.name",         tool_name)
        s.set_attribute("agent.name",        agent_name)
        s.set_attribute("session.id",        session_id)
        s.set_attribute("duration.ms",       str(duration_ms))
        s.set_attribute("success",           str(success))
        s.set_attribute("approval_required", str(approval_required))


# Initialise on import
_provider = setup_tracing()