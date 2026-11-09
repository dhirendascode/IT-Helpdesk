# observability/__init__.py
from observability.tracer import (
    get_tracer,
    span,
    record_agent_span,
    record_tool_span
)

__all__ = [
    "get_tracer",
    "span",
    "record_agent_span",
    "record_tool_span"
]