from pydantic import BaseModel, Field, ConfigDict
from typing import Any
import uuid

class Message(BaseModel):
    """
    One message in the conversation history.
    Every agent appends to this list.
    Never overwrite - always append.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    role: str
    content: str
    agent_name: str | None = None
    
class HelpdeskState(BaseModel):
    """"
    Shared state object for the entire LangGraph workflow.
    
    This is passed to every node (agent) in the graph.
    Each node reads what it needs and writes its results back,
    The orchestrator reads this to decide routing.
    
    Think of it as the single source of truth for one ticket run.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    
    trace_id: str = Field(
        default_factory= lambda: str(uuid.uuid4())
    )
    
    #Ticket Context(Agent reads these but should not modify)
    
    initial_message: str = ""       # raw user query — never change this
    issue_type: str = ""            # e.g. "access_bad_password"
    product_area: str = ""          # e.g. "login_auth"
    priority: str = ""              # "low" | "medium" | "high" | "critical"
    customer_segment: str = ""      # "individual" | "business" | "enterprise"
    sla_plan: str = ""              # "basic" | "business" | "enterprise"
    customer_id: str = "" 
    
    #Agent Flow(Updated as Agent run)
    messages: list[Message] = Field(default_factory=list)
    current_agent: str = ""
    routing_decision: str = ""
    tool_results: dict[str, Any] = {}
    
    #Policy + HITL
    needs_approval: bool = False
    approval_status: str = "not_required"
    # "not_required" | "pending" | "approved" | "denied"
    policy_flags: list[str] = []
    
    #Output
    
    resolution: str | None = None
    groundness_score: float| None = None
    
    #EVAL
    eval_score: float | None = None
    expected_resolution: str = ""
    
    #Error Handling
    error: str | None = None
    retry_count: int = 0