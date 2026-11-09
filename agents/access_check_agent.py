import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.llm_provider import get_llm, get_llm_fast
from core.tool_registry import tool_registry
from core.schemas import ToolCallRequest
from core.state import HelpdeskState, Message

logger = logging.getLogger(__name__)

PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an IT access management specialist.
Your job is to resolve account access issues quickly and securely.

Rules:
- Always recommend self-service password reset first
- For locked accounts: provide exact unlock steps
- For 2FA issues: provide recovery steps
- If granting elevated system access is needed write exactly:
  REQUIRES_HUMAN_APPROVAL: <reason in one line>
- Be empathetic — access issues stop users from working
- Keep response under 150 words"""
    ),
    (
       "human",
        """User Issue:
{issue}

Account Information:
- Account Status  : {account_status}
- SLA Plan        : {sla_tier}
- Priority Support: {priority_support}
- Customer Segment: {customer_segment}

Issue Type: {issue_type}

Provide clear resolution steps.""" 
    )
])

def access_check_agent(state: HelpdeskState) -> HelpdeskState:
    """
    Access Check Agent.
    Handles: access_bad_password, access_locked, access_2fa tickets.
    """
    logger.info(
        f"AcessCheckAgent START | "
        f"session={state.session_id}"
    )
    
    state.current_agent = "access_check_agent"
    state.messages.append(Message(
        role="system",
        content="Access Check Agent Activated",
        agent_name="access_check_agent"
    ))
    
    account_result = tool_registry.execute(ToolCallRequest(
        tool_name="get_account_status",
        parameters={
            "customer_id": state.customer_id or "unknown",
            "sla_plan": state.sla_plan or "basic"
        },
        agent_name="access_check_agent",
        session_id=state.session_id
    ))
    
    if account_result.success:
        account_data = account_result.result
        state.tool_results["get_account_status"] = account_data
    else:
        logger.warning("Account status lookup failed - using defaults")
        account_data = {
            "account_status": "unknown",
            "sla_tier": state.sla_plan or "basic",
            "priority_support": False
        }
        
    chain = PROMPT | get_llm() | StrOutputParser()
    
    try:
        resolution = chain.invoke({
            "issue": state.initial_message,
            "account_status": account_data.get("account_status", "unknown"),
            "sla_tier": account_data.get("sla_tier", "basic"),
            "priority_support": str(account_data.get("priority_support", False)),
            "customer_segment": state.customer_segment or "individual",
            "issue_type": state.issue_type or "access"
        })
        
        if "REQUIRES_HUMAN_APPROVAL" in resolution:
            state.needs_approval = True
            state.approval_status = "pending"
            state.policy_flags.append(
                "access_grant_requires_human_approval"
            )
            logger.warning(
                f"AccessCheckAgent flagged HITL | "
                f"session={state.session_id}"
            )
        
        state.resolution = resolution
        
        state.messages.append(Message(
            role="agent",
            content=resolution,
            agent_name="access_check_agent"
        ))
        
        logger.info(
            f"AccessCheckAgent DONE | "
            f"hitl={state.needs_approval}"
            f"session={state.session_id}"
        )
        
    
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        state.error = str(e)
        state.resolution = "Access Check Agent failed. Please contact support"
    
    
    return state        
    
    