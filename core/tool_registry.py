import yaml
from pathlib import Path
import time
import logging
from core.schemas import (
    ToolDefinition,
    ToolCallRequest as ToolRequest,
    ToolCallResult as ToolResponse
)
from observability.tracer import record_tool_span
logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Central registry for all tools.
    Agents never call tools directly.
    All calls go through here.

    Responsibilities:
    1. Load tool definitions from YAML
    2. Validate tool exists and is enabled
    3. Check if approval is required
    4. Execute the tool implementation
    5. Log every call with timing
    """
    
    
    
    def __init__(self, yaml_path: str = "registry/tools.yaml"):
        self.tools: dict[str, ToolDefinition] = {}
        self._load_tools(yaml_path)
        logger.info(f"ToolRegistry loaded {len(self.tools)} tools")
        
    def _load_tools(self, yaml_path: str):
        TYPE_MAP = {
                "str": str,
                "int": int,
                "bool": bool,
                "list": list,
                "dict": dict,
            }
        path = Path(yaml_path)
        
        if not path:
            raise FileNotFoundError(f"Tool registry file not found {path}")
        
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        for tool in data["tools"]:
            tool["input_schema"] = {
                k: TYPE_MAP[v] for k, v in tool["input_schema"].items()
            }
            tool["output_schema"] = {
                k: TYPE_MAP[v] for k, v in tool["output_schema"].items()
            }
            
        for tool_data in data["tools"]:
            tool = ToolDefinition(**tool_data)
            self.tools[tool.name] = tool
            
    
    def get_tool(self, name : str) -> ToolDefinition | None:
        return self.tools.get(name)
    
    def list_tools(self) -> list[ToolDefinition]:
        return [t for t in self.tools.values if t.enabled]
    
    def requires_approval(self, tool_name: str) -> bool:
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        return tool.approval_required   
    def execute(self, request: ToolRequest) -> ToolResponse:
        """
        THE ONLY WAY TO CALL A TOOL.
        No agent imports tool implementations directly.
        Every call goes through here.

        Flow:
        1. Tool exists?
        2. Tool enabled?
        3. Approval required? → return early, signal HITL
        4. Implementation exists?
        5. Execute with try/except
        6. Return result with timing
        """
        start_time = time.time()

        logger.info(
            f"ToolCall | tool={request.tool_name} | "
            f"agent={request.agent_name} | "
            f"session={request.session_id}"
        )

        # ── Check 1: Tool exists? ──────────────────────────────
        tool = self.get_tool(request.tool_name)
        if not tool:
            logger.error(
                f"Tool not found: {request.tool_name}"
            )
            return ToolResponse(
                tool_name=request.tool_name,
                success=False,
                error=f"Tool '{request.tool_name}' not found in registry"
            )

        # ── Check 2: Tool enabled? ─────────────────────────────
        if not tool.enabled:
            return ToolResponse(
                tool_name=request.tool_name,
                success=False,
                error=f"Tool '{request.tool_name}' is currently disabled"
            )

        # ── Check 3: Approval required? ───────────────────────
        # Return early — do NOT execute
        # Orchestrator sees approval_required=True
        # Triggers HITL interrupt
        if tool.approval_required:
            logger.warning(
                f"HITL required | tool={request.tool_name} | "
                f"session={request.session_id}"
            )
            return ToolResponse(
                tool_name=request.tool_name,
                success=False,
                approval_required=True,
                error=(
                    f"Tool '{request.tool_name}' requires "
                    f"human approval before execution"
                )
            )

        # ── Check 4: Implementation exists? ───────────────────
        # Import here to avoid circular imports
        from core.tool_implementations import TOOL_IMPLEMENTATIONS
        impl = TOOL_IMPLEMENTATIONS.get(request.tool_name)

        if not impl:
            return ToolResponse(
                tool_name=request.tool_name,
                success=False,
                error=(
                    f"No implementation found for "
                    f"tool '{request.tool_name}'"
                )
            )

        # ── Check 5: Execute ───────────────────────────────────
        try:
            result = impl(request.parameters)
            elapsed = (time.time() - start_time) * 1000
            record_tool_span(
                tool_name=request.tool_name,
                session_id=request.session_id,
                agent_name=request.agent_name,
                duration_ms=elapsed,
                success=True
            )
            logger.info(
                f"ToolSuccess | tool={request.tool_name} | "
                f"time={elapsed:.1f}ms"
            )

            return ToolResponse(
                tool_name=request.tool_name,
                success=True,
                result=result,
                execution_time_ms=elapsed
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(
                f"ToolError | tool={request.tool_name} | "
                f"error={str(e)}"
            )
            return ToolResponse(
                tool_name=request.tool_name,
                success=False,
                error=str(e),
                execution_time_ms=elapsed
            )


# ─────────────────────────────────────────────────────────────
# Single instance — loaded once at startup
# Import this everywhere:
#   from core.tool_registry import tool_registry
# Never instantiate ToolRegistry() again anywhere else
# ─────────────────────────────────────────────────────────────

tool_registry = ToolRegistry()