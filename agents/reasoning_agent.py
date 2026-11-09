# agents/reasoning_agent.py
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.llm_provider import get_llm
from core.tool_registry import tool_registry
from core.schemas import ToolCallRequest
from core.state import HelpdeskState, Message

logger = logging.getLogger(__name__)

PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a senior IT systems analyst.
You handle complex, sensitive, and ambiguous IT support tickets.

Rules:
- Think step by step before giving resolution
- For performance issues: identify root cause first then give fix steps
- For security issues: recommend immediate containment first
- For unknown issues: list what information is needed
- Always end with: CONFIDENCE: HIGH / MEDIUM / LOW
- If the issue requires elevated privileges or security review write:
  REQUIRES_HUMAN_APPROVAL: <reason in one line>
- Keep response under 250 words"""
    ),
    (
        "human",
        """User Issue:
{issue}

Policy Check Result:
{policy_result}

Ticket Details:
- Issue Type      : {issue_type}
- Product Area    : {product_area}
- Priority        : {priority}
- Customer Segment: {customer_segment}

Think carefully. Provide your reasoning and resolution steps."""
    )
])

def reasoning_agent(state: HelpdeskState) -> HelpdeskState:
    """
    Reasoning Agent.
    Handles: perf, security, other tickets.
    Uses multi-step reasoning and policy checking
    """
    
    logger.info(
        f"ReasoningAgent START | "
        f"session={state.session_id}"  
    )
    
    state.current_agent = "reasoning_agent"
    state.messages.append(Message(
        role="system",
        content="Reasoning Agent activated",
        agent_name="reasoning_agent"
    ))
    
    policy_result = tool_registry.execute(ToolCallRequest(
        tool_name="check_policy",
        parameters={
            "action":           state.issue_type or "unknown",
            "customer_segment": state.customer_segment or "individual",
            "priority":         state.priority or "medium"
        },
        agent_name="reasoning_agent",
        session_id=state.session_id
    ))
    
    if policy_result.success:
        policy_data = policy_result.result
        state.tool_results["check_policy"] = policy_data
        
        if policy_data.get("requires_hitl"):
            state.needs_approval = True
            state.approval_status = "pending"
            state.policy_flags.append(
                f"policy_requires_hitl: {policy_data.get('reason', '')}"
            )
    else:
        policy_data = {
            "allowed":       True,
            "requires_hitl": False,
            "reason":        "Policy check unavailable — defaulting to allow"
        } 
        
    is_security = (
        "security" in (state.issue_type or "").lower() or
        (state.issue_type or "").startswith("security")
    )
    
    if is_security:
        state.needs_approval = True
        state.approval_status = "pending"
        state.policy_flags.append(
            "security_incident_always_requires_human_approval"
        )
        # Attempt to flag as security incident
        # This tool requires approval so registry returns early
        # That is expected — we just want it logged
        
        tool_registry.execute(ToolCallRequest(
            tool_name="flag_security_incident",
            parameters={
                "ticket_id":     state.session_id,
                "incident_type": state.issue_type or "unknown",
                "severity":      state.priority or "medium" 
            },
            agent_name="reasoning_agent",
            session_id=state.session_id
        ))
        logger.warning(
            f"Security ticket — HITL mandatory | "
            f"session={state.session_id}"
        )
        
    chain = PROMPT | get_llm() | StrOutputParser()
    
    try:
        resolution = chain.invoke({
            "issue":            state.initial_message,
            "policy_result":    str(policy_data),
            "issue_type":       state.issue_type or "unknown",
            "product_area":     state.product_area or "unknown",
            "priority":         state.priority or "medium",
            "customer_segment": state.customer_segment or "individual"
        })
        
        if "REQUIRES_HUMAN_APPROVAL" is resolution:
            state.needs_approval = True
            state.approval_status = "pending"
            state.policy_flags.append(
                "llm_flagged_requires_human_approval"
            )
            
        state.resolution = resolution
        state.messages.append(Message(
            role="agent",
            content=resolution,
            agent_name="reasoning_agent"
        ))

        logger.info(
            f"ReasoningAgent DONE | "
            f"hitl={state.needs_approval} | "
            f"flags={state.policy_flags} | "
            f"session={state.session_id}"
        )
    
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        state.error = str(e)
        state.resolution = "Reasoning failed. Please escalate to human agent."

    return state
    
    
    