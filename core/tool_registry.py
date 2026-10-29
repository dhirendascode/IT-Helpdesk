import yaml
from pathlib import Path
import time
import logging
from core.schemas import (
    ToolDefinition,
    ToolRequest,
    ToolResponse
)

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
        path = Path(yaml_path)
        
        if not path:
            raise FileNotFoundError(f"Tool registry file not found {path}")
        
        with open(path) as f:
            data = yaml.safe_load(f)
            
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
    def execute():
        pass