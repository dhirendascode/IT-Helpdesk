# core/tools.py
#
# @tool decorated wrappers for LLM tool selection.
#
# IMPORTANT: These functions do NOT contain business logic.
# They are thin wrappers around tool_registry.execute().
# All policy enforcement happens in tool_registry.
# The LLM reads docstrings to decide when to call each tool.
# Docstrings here are written FOR THE LLM — not for humans.

from langchain_core.tools import tool
from core.tool_registry import tool_registry
from core.schemas import ToolCallRequest
import logging

logger = logging.getLogger(__name__)

def _execute(
    tool_name: str,
    parameters: dict,
    agent_name: str = "unknown_agent",
    session_id: str = "unknown_session"
) -> str:
    """
    Route tool call through registry.
    Returns string result for LLM consumption
    """
    result = tool_registry.execute(ToolCallRequest(
        tool_name=tool_name,
        parameters=parameters,
        agent_name=agent_name,
        session_id=session_id
    ))
    if result.approval_required:
        return (
            f"REQUIRES_HUMAN_APPROVAL: "
            f"Tool '{tool_name}' needs human approval "
            f"before execution. Trigger HITL process."
        )
        
    if not result.success:
        return f"Tool error: {result.error}"
    
    if result.result:
        return "\n".join(
            f"{k}: {v}"
            for k, v in result.result.items()
        )
        
    return "Tool executed successfully"

@tool
def knowledge_search(query: str, top_k: int = 3) -> str:
    """
    Search past resolved IT support tickets for similar issues.

    Use this tool when:
    - User reports a bug or application error
    - User asks how to do something (howto questions)
    - User asks about a feature
    - You need context from past resolutions to answer

    Args:
        query: The user issue in natural language
        top_k: Number of similar tickets to find (default 3)

    Returns:
        Similar past resolutions ranked by relevance
    """
    
    return _execute(
        tool_name="knowledge_search",
        parameters={"query": query, "top_k": top_k}
    )

@tool
def get_account_status(customer_id: str, sla_plan: str) -> str:
    """
    Get customer account health and SLA information.

    Use this tool when:
    - User has a login or access problem
    - You need to know the customer SLA tier
    - You need to check if priority support applies
    - User has a billing question needing account context

    Args:
        customer_id: Customer unique ID (e.g. CUST_001)
        sla_plan: Customer SLA plan (standard/business/enterprise)

    Returns:
        Account status, SLA tier, and support entitlements
    """
    return _execute(
        tool_name= "get_account_status",
        parameters={
            "customer_id": customer_id,
            "sla_plan": sla_plan
        }
    )
    
@tool
def check_policy(
    action: str,
    customer_segment: str,
    priority: str
) -> str:
    """
    Check if an action is permitted by policy rules.

    ALWAYS call this before taking any sensitive action.
    The policy engine may require human approval.

    Use this tool when:
    - You are about to grant access to a system
    - You are handling a security related ticket
    - You are unsure if an action needs approval
    - Ticket involves elevated permissions

    Args:
        action: The action you want to take
        customer_segment: Customer segment (individual/business/enterprise)
        priority: Ticket priority (low/medium/high/critical)

    Returns:
        ALLOWED or REQUIRES_HUMAN_APPROVAL with reason
    """
    return _execute(
        tool_name="check_policy",
        parameters={
            "action":           action,
            "customer_segment": customer_segment,
            "priority":         priority
        }
    )
@tool
def create_ticket(
    issue_summary: str,
    priority: str,
    customer_id: str
) -> str:
    """
    Create a new escalation ticket in the helpdesk system.

    Use this tool when:
    - Issue cannot be resolved automatically
    - Billing issue needs manual processing by billing team
    - User needs to be contacted by a human agent
    - Issue requires specialist intervention

    Args:
        issue_summary: Clear description of the issue
        priority: Ticket priority (low/medium/high/critical)
        customer_id: Customer identifier

    Returns:
        New ticket ID and confirmation
    """
    return _execute(
        tool_name="create_ticket",
        parameters={
            "issue_summary": issue_summary,
            "priority":      priority,
            "customer_id":   customer_id
        }
    )
    
@tool
def reset_password(customer_id: str, method: str = "email") -> str:
    """
    Trigger a password reset for a customer account.

    Use this tool when:
    - User cannot login due to forgotten password
    - User says their password stopped working
    - Account requires credential reset

    Args:
        customer_id: Customer unique ID
        method: Reset delivery method — email or sms

    Returns:
        Reset confirmation and instructions
    """
    return _execute(
        tool_name="reset_password",
        parameters={
            "customer_id": customer_id,
            "method":      method
        }
    )
    
@tool
def flag_security_incident(
    ticket_id: str,
    incident_type: str,
    severity: str
) -> str:
    """
    Flag a ticket as a security incident for immediate review.

    ALWAYS use this for security related tickets.
    This tool REQUIRES human approval — it will trigger HITL.

    Use this tool when:
    - Suspicious login activity detected
    - Potential security vulnerability reported
    - Compliance violation suspected
    - Unauthorized access attempt

    Args:
        ticket_id: Session or ticket identifier
        incident_type: Type of security incident
        severity: Severity level (low/medium/high/critical)

    Returns:
        Incident ID and escalation confirmation
    """
    return _execute(
        tool_name="flag_security_incident",
        parameters={
            "ticket_id":     ticket_id,
            "incident_type": incident_type,
            "severity":      severity
        }
    )

#TOOL_GROUPS

KNOWLEDGE_TOOLS = [knowledge_search]

ACCESS_TOOLS = [
    get_account_status,
    reset_password,
    check_policy
]

REASONING_TOOLS = [
    check_policy,
    flag_security_incident,
    create_ticket
]

BILLING_TOOLS = [
    get_account_status,
    create_ticket
]

# All tools — for MCP server and registry listing
ALL_TOOLS = [
    knowledge_search,
    get_account_status,
    check_policy,
    create_ticket,
    reset_password,
    flag_security_incident
]