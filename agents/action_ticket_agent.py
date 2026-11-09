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
        """You are a billing and accounts specialist.
Your job is to resolve billing issues efficiently and professionally.

Rules:
- Always verify account details before recommending action
- For duplicate charges: explain refund process clearly
- For downgrade requests: confirm steps to process it
- For invoice questions: explain the charges clearly
- If the issue needs manual processing by billing team write exactly:
  CREATE_TICKET: <reason in one line>
  Then continue with what the user should expect next
- Be professional and reassuring — billing issues cause anxiety
- Keep response under 200 words""" 
    ),
    (
         "human",
        """User Issue:
{issue}

Account Information:
- SLA Plan        : {sla_tier}
- Account Status  : {account_status}
- Priority Support: {priority_support}
- Customer Segment: {customer_segment}

Issue Type: {issue_type}

Provide resolution. If manual processing needed start with CREATE_TICKET."""
    )
])

def action_ticket_agent(state: HelpdeskState) -> HelpdeskState:
    """
    Action/Ticket Agent.
    Handles: billing_double_charge, billing_downgrade,
             billing_invoice tickets.
    """
    
    logger.info(
        f"ActionTicketAgent START | "
        f"session={state.session_id}"
    )
    
    state.current_agent = "action_ticket_agent"
    state.messages.append(Message(
        role="system",
        content="Action/Ticket Agent activated",
        agent_name="action_ticket_agent"
    ))
    
    account_result = tool_registry.execute(ToolCallRequest(
        tool_name="get_account_status",
        parameters={
            "customer_id": state.customer_id or "unknown",
            "sla_plan": state.sla_plan or "basic"
        },
        agent_name="action_ticket_agent",
        session_id=state.session_id
    ))
    
    if account_result.success:
        account_data = account_result.result
        state.tool_results["get_account_status"] = account_data
    else:
        account_data = {
            "account_status": "unknown",
            "sla_tier": state.sla_plan or "basic",
            "priority_support": False
        }
        
    chain = PROMPT | get_llm() | StrOutputParser()
    
    try:
        resolution = chain.invoke({
            "issue": state.initial_message,
            "sla_tier": account_data.get("sla_tier", "basic"),
            "account_status": account_data.get("account_status", "unknown"),
            "priority_support": str(account_data.get("priority_support", False)),
            "customer_segment": state.customer_segment or "individual",
            "issue_type": state.issue_type or "billing"
        })
        
        if "CREATE_TICKET" in resolution:
            reason = (
                resolution
                .split("CREATE_TICKET:")[1]
                .split("\n")[0]
                .strip()
            )
            
            ticket_result = tool_registry.execute(ToolCallRequest(
                tool_name="create_ticket",
                parameters={
                    "issue_summary": reason,
                    "priority": state.priority or "medium",
                    "customer_id": state.customer_id or "unknown"
                },
                agent_name="action_ticket_agent",
                session_id=state.session_id
            ))
            
            if ticket_result.success:
                ticket_id = ticket_result.result.get("ticket_id")
                state.tool_results["create_ticket"] = ticket_result.result
                
                resolution = (
                    f"{resolution}\n\n"
                    f"Escalation ticket created: {ticket_id}\n"
                    f"Our billing team will contact you within "
                    f"{account_data.get('sla_hours',24)} hours."
                )
                
                logger.info(
                    f"Ticket created: {ticket_id} | "
                    f"session: {state.session_id}"
                )
        state.resolution = resolution
        state.messages.append(Message(
                role="agent",
                content=resolution,
                agent_name="action_ticket_agent"
            ))
            
        logger.info(
                f"ActionTicketAgent DONE | "
                f"session={state.session_id}"
            )
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        state.error = str(e)
        state.resolution = "Billing action failed. Please contact support"
        
    return state