# core/schemas.py
from pydantic import BaseModel, ConfigDict
from typing import Any

# ── Tool Registry Schemas ──────────────────────────────────────

class ToolDefinition(BaseModel):
    """
    One tool entry loaded from registry/tools.yaml.
    Validated at startup — bad YAML = clear error immediately.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    version: str
    approval_required: bool
    enabled: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolCallRequest(BaseModel):
    """
    What an agent sends when it wants to call a tool.

    Why agent_name and session_id?
    → Every tool call is logged with these
    → You can trace exactly which agent called which tool
    → Essential for debugging and audit
    """
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    parameters: dict[str, Any]
    agent_name: str
    session_id: str


class ToolCallResult(BaseModel):
    """
    What the registry returns after executing a tool.

    success=True  → result has the data
    success=False → error has the message
                    OR approval_required=True means HITL needed
    """
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_required: bool = False
    execution_time_ms: float = 0.0


# ── Routing Schemas ────────────────────────────────────────────

class RoutingDecision(BaseModel):
    """
    Output of the orchestrator routing logic.
    Tells the graph which agent node to execute next.

    confidence → how sure the router is
    reasoning  → why this agent was chosen
                 shown in dashboard for transparency
    """
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    scenario_prefix: str
    confidence: float          # 0.0 → 1.0
    requires_hitl: bool
    reasoning: str