from pydantic import BaseModel
from typing import Any

class ToolDefinition(BaseModel):
    """
    Represents one tool entry from tools.yaml
"""
    name:str
    description:str
    version:str
    approval_required:bool
    enabled:bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    
class ToolRequest(BaseModel):
    """
     What an agent sends when it wants to call a tool
    """
    tool_name:str
    parameters: dict[str, Any]
    agent_name:str
    session_id:str
    
class ToolResponse(BaseModel):
    """
    What registry return when after executing a tool
    """
    tool_name:str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_required: bool
    execution_time_ms: float = 0.0
    
    
    