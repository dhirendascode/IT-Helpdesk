import sys
import logging
sys.path.append(".")

from fastmcp import FastMCP
from config import settings

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="IT Helpdesk Agent",
    instructions=(
        "Use these tools to resolve IT support tickets. "
        "Start with submit_helpdesk_ticket for a complete "
        "resolution, or use individual tools for specific task."
    )
)

# ─────────────────────────────────────────────────────────────
# TOOLS
#
# @mcp.tool() does three things:
# 1. Registers the function as an MCP tool
# 2. Uses type hints to generate inputSchema automatically
# 3. Uses docstring as tool description for LLM
#
# FastMCP handles everything else.
# ─────────────────────────────────────────────────────────────


@mcp.tool
def submit_helpdesk_ticket(
    initial_message: str,
    priority: str = "medium",
    customer_segment: str = "individual",
    sla_plan:         str = "standard",
    customer_id:      str = "unknown"
) -> str:
    """
    Submit a full IT support ticket through the multi-agent system.
    
    This is the primary tool. Use this when a user has an IT issue.
    The system automatically:
    - Classifies the ticket type
    - Routes to the right specialist agent
    - Searches past resolution
    - Generates a resolution
    - Flags for human approval if needed
    
    Returns complete resolution or pending approval status.
    """
    from core.orchestrator import run_ticket
    
    logger.info(f"MCP: submit_helpdesk_ticket | msg={initial_message[:50]}")
    
    state, interrupts = run_ticket(
        initial_message=initial_message,
        priority=priority,
        customer_segment=customer_segment,
        sla_plan=sla_plan,
        customer_id=customer_id
    )
    
    if state.needs_approval or interrupts:
        return(
            f"PENDING HUMAN APPROVAL\n"
            f"Session ID : {state.session_id}\n"
            f"Agent Used :  {state.current_agent}\n"
            f"Issue Type : {state.issue_type}\n"
            f"Flags : {','.join(state.policy_flags)}\n"
            f"Drafts: {state.resolution}\n\n"
            f"Use approve_ticket tool with this session ID"
        )
        
    return(
        f"RESOLVED\n"
        f"Session ID   : {state.session_id}\n"
        f"Agent Used   : {state.current_agent}\n"
        f"Issue Type   : {state.issue_type}\n"
        f"Groundedness : {state.groundness_score}\n\n"
        f"Resolution:\n{state.resolution}"
    )

@mcp.tool()
def knowledge_search(
    query: str,
    top_k:int = 3
) -> str:
    """
    Search past resolved IT tickets for similar issues.

    Use when:
    - User has a bug or application error
    - User asks how to do something
    - You need context from past resolutions

    Returns similar past resolutions ranked by relevance.
    """
    from vector_store.vector_store import get_vector_store
    
    logger.info(f"MCP: knowledge_search | query={query[:50]}")
    
    store = get_vector_store()
    results = store.similarity_search_with_score(query, k=top_k)
    
    if not results:
        return "No similar past resolutions found."
    
    parts = []
    for i, (doc, score) in enumerate(results, 1):
        parts.append(
            f"Result {i}:\n"
            f"Scenario : {doc.metadata.get('scenario_key', 'unknown')}\n"
            f"Resolution: {doc.metadata.get('resolution_summary', 'N/A')}"
        )
        
    return "\n\n".join(parts)

@mcp.tool()
def get_account_status(
    customer_id: str,
    sla_plan: str
) -> str:
    """
    Get customer account health and SLA information.

    Use when:
    - User has a login or access problem
    - You need to know the customer SLA tier
    - User has a billing question needing account context

    Returns account status, SLA tier, and support entitlements.
    """
    from core.tool_registry import tool_registry
    from core.schemas import ToolCallRequest

    logger.info(f"MCP: get_account_status | customer={customer_id}")

    result = tool_registry.execute(ToolCallRequest(
        tool_name="get_account_status",
        parameters={
            "customer_id": customer_id,
            "sla_plan":    sla_plan
        },
        agent_name="mcp_client",
        session_id="mcp_session"
    ))

    if not result.success:
        return f"Error: {result.error}"

    return "\n".join(
        f"{k}: {v}" for k, v in result.result.items()
    )
@mcp.tool()
def check_policy(
    action:           str,
    customer_segment: str,
    priority:         str
) -> str:
    """
    Check if an action is permitted by policy rules.

    Always call this before taking sensitive actions.
    Returns ALLOWED or REQUIRES_HUMAN_APPROVAL with reason.

    Use when:
    - About to grant system access
    - Handling a security related ticket
    - Unsure if an action needs human approval
    """
    from core.tool_registry import tool_registry
    from core.schemas import ToolCallRequest

    logger.info(f"MCP: check_policy | action={action}")

    result = tool_registry.execute(ToolCallRequest(
        tool_name="check_policy",
        parameters={
            "action":           action,
            "customer_segment": customer_segment,
            "priority":         priority
        },
        agent_name="mcp_client",
        session_id="mcp_session"
    ))

    if not result.success:
        return f"Error: {result.error}"

    return "\n".join(
        f"{k}: {v}" for k, v in result.result.items()
    )


@mcp.tool()
def create_ticket(
    issue_summary: str,
    priority:      str,
    customer_id:   str
) -> str:
    """
    Create a new escalation ticket in the helpdesk system.

    Use when:
    - Issue cannot be resolved automatically
    - Billing issue needs manual processing
    - User needs to be contacted by a human agent

    Returns new ticket ID and confirmation.
    """
    from core.tool_registry import tool_registry
    from core.schemas import ToolCallRequest

    logger.info(f"MCP: create_ticket | customer={customer_id}")

    result = tool_registry.execute(ToolCallRequest(
        tool_name="create_ticket",
        parameters={
            "issue_summary": issue_summary,
            "priority":      priority,
            "customer_id":   customer_id
        },
        agent_name="mcp_client",
        session_id="mcp_session"
    ))

    if not result.success:
        return f"Error: {result.error}"

    return "\n".join(
        f"{k}: {v}" for k, v in result.result.items()
    )


@mcp.tool()
def reset_password(
    customer_id: str,
    method:      str = "email"
) -> str:
    """
    Trigger a password reset for a customer account.

    Use when:
    - User cannot login due to forgotten password
    - User says their password stopped working
    - Account requires credential reset

    Returns reset confirmation and instructions.
    """
    from core.tool_registry import tool_registry
    from core.schemas import ToolCallRequest

    logger.info(f"MCP: reset_password | customer={customer_id}")

    result = tool_registry.execute(ToolCallRequest(
        tool_name="reset_password",
        parameters={
            "customer_id": customer_id,
            "method":      method
        },
        agent_name="mcp_client",
        session_id="mcp_session"
    ))

    if not result.success:
        return f"Error: {result.error}"

    return "\n".join(
        f"{k}: {v}" for k, v in result.result.items()
    )


@mcp.tool()
def approve_ticket(
    session_id: str,
    approved:   bool,
    reason:     str = ""
) -> str:
    """
    Approve or deny a ticket pending human review.

    Use after submit_helpdesk_ticket returns PENDING HUMAN APPROVAL.
    Pass the session_id from that response.

    Returns final resolution after human decision.
    """
    from core.orchestrator import resume_ticket

    logger.info(
        f"MCP: approve_ticket | "
        f"session={session_id} | approved={approved}"
    )

    state, _ = resume_ticket(
        session_id=session_id,
        approved=approved,
        reason=reason or (
            "Approved via MCP" if approved else "Denied via MCP"
        )
    )

    return (
        f"Decision   : {'APPROVED' if approved else 'DENIED'}\n"
        f"Session ID : {state.session_id}\n"
        f"Status     : {state.approval_status}\n\n"
        f"Resolution:\n{state.resolution}"
    )


@mcp.tool()
def list_sessions(limit: int = 10) -> str:
    """
    List recent IT support ticket sessions.

    Use to check recent ticket history.
    Returns session summaries sorted newest first.
    """
    from evaluation.session_store import session_store

    sessions = session_store.list_sessions()[:limit]

    if not sessions:
        return "No sessions found."

    lines = [f"Found {len(sessions)} recent sessions:\n"]
    for s in sessions:
        lines.append(
            f"Session : {s['session_id'][:16]}...\n"
            f"Issue   : {s['issue_type']}\n"
            f"Agent   : {s['agent_used']}\n"
            f"HITL    : {s['needs_approval']}\n"
            f"Score   : {s['eval_score']}\n"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    logger.info("IT Helpdesk MCP Server starting...")
    mcp.run()