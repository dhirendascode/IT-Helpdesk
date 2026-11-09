# observability/tracer.py
import time
import logging
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor
)
from opentelemetry.sdk.resources import Resource
from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# SETUP
# Called once at startup
# Configures where traces are exported
# ─────────────────────────────────────────────────────────────

def setup_tracing() -> TracerProvider:
    """
    Sets up OpenTelemetry tracing.
    Called once when app starts.

    Export targets:
    console → prints spans to terminal (dev)
    file    → writes spans to file (prod)
    """
    resource = Resource.create({
        "service.name":    "it-helpdesk-agent",
        "service.version": "1.0.0",
        "deployment.env":  "development"
    })

    provider = TracerProvider(resource=resource)

    if settings.otel_export == "file":
        # Write spans to file for later analysis
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor
        )
        import json

        class FileSpanExporter:
            """Simple file exporter — writes one JSON per span."""

            def __init__(self, path: str = "data/traces.jsonl"):
                self.path = path

            def export(self, spans):
                with open(self.path, "a") as f:
                    for span in spans:
                        f.write(json.dumps({
                            "name":       span.name,
                            "trace_id":   format(span.context.trace_id, "032x"),
                            "span_id":    format(span.context.span_id, "016x"),
                            "start_time": span.start_time,
                            "end_time":   span.end_time,
                            "duration_ms": (
                                span.end_time - span.start_time
                            ) / 1_000_000,
                            "attributes": dict(span.attributes or {}),
                            "status":     span.status.status_code.name
                        }) + "\n")
                return 0  # SUCCESS

            def shutdown(self):
                pass

            def force_flush(self, timeout_millis=30000):
                pass

        provider.add_span_processor(
            SimpleSpanProcessor(FileSpanExporter())
        )
        logger.info("OTEL: exporting to file → data/traces.jsonl")

    else:
        # Console export — prints spans to terminal
        provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )
        logger.info("OTEL: exporting to console")

    trace.set_tracer_provider(provider)
    return provider


# ─────────────────────────────────────────────────────────────
# TRACER INSTANCE
# Get this in any file that needs to create spans
# Usage:
#   from observability.tracer import get_tracer
#   tracer = get_tracer()
# ─────────────────────────────────────────────────────────────

def get_tracer() -> trace.Tracer:
    return trace.get_tracer("it-helpdesk-agent")


# ─────────────────────────────────────────────────────────────
# HELPER — SPAN CONTEXT MANAGER
# Wraps a code block in a span
# Automatically records timing and errors
#
# Usage:
#   with span("my_operation", {"key": "value"}):
#       do_something()
# ─────────────────────────────────────────────────────────────

@contextmanager
def span(name: str, attributes: dict = None):
    """
    Context manager that wraps code in an OTEL span.
    Records timing automatically.
    Records exceptions automatically.

    Usage:
        with span("tool.knowledge_search", {"session_id": sid}):
            result = knowledge_search(query)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        try:
            yield s
        except Exception as e:
            s.record_exception(e)
            s.set_status(
                trace.StatusCode.ERROR,
                str(e)
            )
            raise


# ─────────────────────────────────────────────────────────────
# HELPER — RECORD AGENT SPAN
# Convenience function for agent nodes
# Standardises attribute names across all agents
# ─────────────────────────────────────────────────────────────

def record_agent_span(
    agent_name: str,
    session_id: str,
    duration_ms: float,
    success: bool,
    extra: dict = None
):
    """
    Records a completed agent execution as a span.
    Called at the end of every agent function.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(
        f"agent.{agent_name}"
    ) as s:
        s.set_attribute("agent.name",       agent_name)
        s.set_attribute("session.id",       session_id)
        s.set_attribute("duration.ms",      str(duration_ms))
        s.set_attribute("success",          str(success))

        if extra:
            for k, v in extra.items():
                s.set_attribute(k, str(v))


# ─────────────────────────────────────────────────────────────
# HELPER — RECORD TOOL SPAN
# Convenience function for tool calls
# ─────────────────────────────────────────────────────────────

def record_tool_span(
    tool_name: str,
    session_id: str,
    agent_name: str,
    duration_ms: float,
    success: bool,
    approval_required: bool = False
):
    """
    Records a tool call as a span.
    Called by tool_registry after every execution.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(
        f"tool.{tool_name}"
    ) as s:
        s.set_attribute("tool.name",         tool_name)
        s.set_attribute("agent.name",        agent_name)
        s.set_attribute("session.id",        session_id)
        s.set_attribute("duration.ms",       str(duration_ms))
        s.set_attribute("success",           str(success))
        s.set_attribute("approval_required", str(approval_required))


# ─────────────────────────────────────────────────────────────
# INITIALISE ON IMPORT
# Tracing is set up as soon as this module is imported
# ─────────────────────────────────────────────────────────────

_provider = setup_tracing()