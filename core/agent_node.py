import time
import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from core.llm_provider import get_llm
from core.tool_registry import tool_registry
from core.schemas import ToolCallRequest
from core.state import HelpdeskState, Message
from core.tools import (
    KNOWLEDGE_TOOLS,
    ACCESS_TOOLS,
    REASONING_TOOLS,
    BILLING_TOOLS
)
logger = logging.getLogger(__name__)
from config import settings
MAX_TOOL_RETRIES = settings.max_tool_retries

# ─────────────────────────────────────────────────────────────
# AGENT CONFIGURATION
#
# Each agent has:
# → system_prompt : its role, rules, and constraints
# → tools         : which tools it can suggest to call
#
# Adding a new agent = add one entry here
# No other file needs to change

# core/agent_node.py

AGENT_CONFIG = {

    "knowledge_search_agent": {
        "tools": KNOWLEDGE_TOOLS,
        "system_prompt": """You are a senior IT helpdesk specialist.
Resolve IT support tickets using your available tools to find past resolutions.

Rules:
- Always search for similar past resolutions first
- Base your resolution ONLY on what the tools return
- Give exact numbered steps — not vague advice
- If no relevant past resolution found say so clearly
- Keep response under 200 words
- Never make up steps not supported by retrieved context"""
    },

    "access_check_agent": {
        "tools": ACCESS_TOOLS,
        "system_prompt": """You are an IT access management specialist.
Resolve account access and login issues using your available tools.

Rules:
- Always check account status before recommending action
- For password issues use the password reset tool
- Always check policy before granting access
- If policy requires human approval — stop and state this clearly
- Be empathetic — access issues stop users from working
- Keep response under 150 words"""
    },

    "reasoning_agent": {
        "tools": REASONING_TOOLS,
        "system_prompt": """You are a senior IT systems analyst.
Handle complex, sensitive, and security-related tickets using your available tools.

Rules:
- Always check policy before any sensitive action
- For security tickets always flag as security incident
- Think step by step — state your reasoning
- End with: CONFIDENCE: HIGH / MEDIUM / LOW
- Keep response under 250 words"""
    },

    "action_ticket_agent": {
        "tools": BILLING_TOOLS,
        "system_prompt": """You are a billing and accounts specialist.
Resolve billing issues using your available tools.

Rules:
- Always verify account details before recommending action
- Create escalation tickets for issues needing manual processing
- Be professional and reassuring
- Keep response under 200 words"""
    }
}

def build_tool_context(tools : list) -> str:
    """
    Generates tool description block from actual bound tools.
    Injected into every agent's human message at runtime.

    Why runtime not prompt time?
    → Source of truth is the tools list
    → Adding/removing a tool auto-updates all agents
    → No manual prompt maintenance needed
    → Works for 5 agents or 500 agents
    """
    if not tools:
        return "You have no tools available, Answer from you knowledge only."
    
    lines = ["You have access to only the tools : "]
    
    for tool in tools:
        doc = (tool.description or "").strip().split("\n")[0]
        lines.append(f"- {tool.name}: {doc}")
    
    lines.append(
        "\nIMPORTANT: Only call tools from this list. "
        "Do not call any other tool name."
    )

    return "\n".join(lines)

def execute_tool_calls(
    tool_calls: list,
    tools: list,
    agent_name: str,
    state: HelpdeskState
) -> tuple[list, bool, str]:
    """
    Execute one round of LLM tool calls.

    Fix 2: validates tool name before execution.
    Returns error flag so caller can trigger Fix 3 retry.

    Returns:
        tool_messages : list of ToolMessage to add to history
        has_error     : True if any hallucination detected
        error_detail  : description of error for retry prompt
    """
    tool_messages = []
    has_error     = False
    error_detail  = ""

    valid_tool_names = [t.name for t in tools]

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id   = tool_call["id"]

        # ── FIX 2 — Validate tool name ────────────────────────
        if tool_name not in valid_tool_names:
            has_error    = True
            error_detail = (
                f"Tool '{tool_name}' does not exist. "
                f"You must only use: {', '.join(valid_tool_names)}."
            )

            logger.warning(
                f"{agent_name} hallucinated tool: '{tool_name}' | "
                f"valid: {valid_tool_names}"
            )

            tool_messages.append(ToolMessage(
                content=error_detail,
                tool_call_id=tool_id
            ))
            continue

        # ── Execute via registry ──────────────────────────────
        registry_result = tool_registry.execute(
            ToolCallRequest(
                tool_name=tool_name,
                parameters=tool_args,
                agent_name=agent_name,
                session_id=state.session_id
            )
        )

        # Store in state for observability
        state.tool_results[tool_name] = (
            registry_result.result
            if registry_result.success
            else {"error": registry_result.error}
        )

        # Handle approval required
        if registry_result.approval_required:
            state.needs_approval  = True
            state.approval_status = "pending"
            state.policy_flags.append(
                f"{tool_name}_requires_human_approval"
            )
            tool_result_str = (
                f"REQUIRES_HUMAN_APPROVAL: "
                f"Tool '{tool_name}' needs human approval "
                f"before execution."
            )

        elif registry_result.success:
            tool_result_str = "\n".join(
                f"{k}: {v}"
                for k, v in (registry_result.result or {}).items()
            )

        else:
            tool_result_str = f"Tool error: {registry_result.error}"
            has_error    = True
            error_detail = tool_result_str

        tool_messages.append(ToolMessage(
            content=tool_result_str,
            tool_call_id=tool_id
        ))

    return tool_messages, has_error, error_detail


# ─────────────────────────────────────────────────────────────
# AGENT FACTORY
# Returns a LangGraph node function for the given agent name
# ─────────────────────────────────────────────────────────────
def build_agent_node(agent_name: str):
    """
    Factory function.
    Returns a LangGraph node function for the given agent.
    """
    config        = AGENT_CONFIG[agent_name]
    tools         = config["tools"]
    system_prompt = config["system_prompt"]

    # Bind tools to LLM
    llm_with_tools = get_llm().bind_tools(tools)

    def agent_node(state: HelpdeskState) -> HelpdeskState:
        start_time = time.time()

        logger.info(
            f"{agent_name} START | "
            f"session={state.session_id}"
        )

        state.current_agent = agent_name
        state.messages.append(Message(
            role="system",
            content=f"{agent_name} activated",
            agent_name=agent_name
        ))

        # ── Build initial messages ────────────────────────────
        # Tool context auto-generated from actual tools list
        # Never hardcoded — scales to any number of tools
        tool_context = build_tool_context(tools)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=(
                f"{tool_context}\n\n"
                f"Issue       : {state.initial_message}\n"
                f"Priority    : {state.priority or 'medium'}\n"
                f"Segment     : {state.customer_segment or 'individual'}\n"
                f"SLA Plan    : {state.sla_plan or 'basic'}\n"
                f"Customer ID : {state.customer_id or 'unknown'}\n"
                f"Issue Type  : {state.issue_type or 'unknown'}"
            ))
        ]

        try:
            resolution  = None
            retry_count = 0

            # ── FIX 3 — RETRY LOOP ────────────────────────────
            # Attempts up to MAX_TOOL_RETRIES times
            # Each iteration:
            #   → Call LLM
            #   → Execute tool calls (with Fix 2 validation)
            #   → If error → add correction → retry
            #   → If clean → get final resolution → break
            # ─────────────────────────────────────────────────

            while retry_count < MAX_TOOL_RETRIES:

                # ── LLM call ──────────────────────────────────
                response = llm_with_tools.invoke(messages)

                # ── No tool calls → direct answer ─────────────
                if not (
                    hasattr(response, "tool_calls")
                    and response.tool_calls
                ):
                    resolution = response.content
                    logger.info(
                        f"{agent_name} answered directly | "
                        f"attempt={retry_count + 1}"
                    )
                    break

                # ── Tool calls requested ──────────────────────
                logger.info(
                    f"{agent_name} tool calls: "
                    f"{[tc['name'] for tc in response.tool_calls]} | "
                    f"attempt={retry_count + 1}"
                )

                # Add LLM response to message history
                messages.append(response)

                # Execute tool calls — Fix 2 validates names
                tool_messages, has_error, error_detail = (
                    execute_tool_calls(
                        tool_calls=response.tool_calls,
                        tools=tools,
                        agent_name=agent_name,
                        state=state
                    )
                )

                # Add all tool results to message history
                messages.extend(tool_messages)

                # ── Error detected → Fix 3 retry ──────────────
                if has_error:
                    retry_count += 1

                    if retry_count < MAX_TOOL_RETRIES:
                        # Add explicit correction message
                        # LLM reads this and corrects itself
                        correction = (
                            f"Attempt {retry_count} failed: "
                            f"{error_detail}\n\n"
                            f"Available tools: "
                            f"{', '.join(t.name for t in tools)}.\n"
                            f"Please retry using only "
                            f"the available tools."
                        )

                        messages.append(
                            HumanMessage(content=correction)
                        )

                        logger.warning(
                            f"{agent_name} retrying | "
                            f"attempt={retry_count} | "
                            f"reason={error_detail[:80]}"
                        )
                        continue

                    else:
                        # Max retries reached
                        logger.error(
                            f"{agent_name} max retries reached | "
                            f"session={state.session_id}"
                        )
                        resolution = (
                            "I was unable to process this request "
                            "after multiple attempts. "
                            "Escalating to a human agent."
                        )
                        state.needs_approval  = True
                        state.approval_status = "pending"
                        state.policy_flags.append(
                            f"{agent_name}_max_retries_exceeded"
                        )
                        break

                # ── Clean execution → get final resolution ─────
                # All tools executed successfully
                # Ask LLM to synthesize final answer
                final_response = get_llm().invoke(messages)
                resolution     = final_response.content

                logger.info(
                    f"{agent_name} resolved | "
                    f"attempt={retry_count + 1} | "
                    f"tools_used={list(state.tool_results.keys())}"
                )
                break

            # ── Handle HITL signal in resolution ─────────────
            if resolution and "REQUIRES_HUMAN_APPROVAL" in resolution:
                state.needs_approval  = True
                state.approval_status = "pending"
                state.policy_flags.append(
                    f"{agent_name}_llm_flagged_hitl"
                )

            # ── Write to state ────────────────────────────────
            state.resolution = resolution or (
                "Unable to generate resolution. "
                "Please contact support."
            )

            state.messages.append(Message(
                role="agent",
                content=state.resolution,
                agent_name=agent_name
            ))

            elapsed = (time.time() - start_time) * 1000
            logger.info(
                f"{agent_name} DONE | "
                f"time={elapsed:.0f}ms | "
                f"retries={retry_count} | "
                f"hitl={state.needs_approval} | "
                f"session={state.session_id}"
            )

        except Exception as e:
            logger.error(
                f"{agent_name} crashed: {e} | "
                f"session={state.session_id}"
            )
            state.error      = str(e)
            state.resolution = (
                "Agent error. Please retry or contact support."
            )

        return state

    agent_node.__name__ = agent_name
    return agent_node


# ─────────────────────────────────────────────────────────────
# BUILT NODES — import these in orchestrator.py
# ─────────────────────────────────────────────────────────────

knowledge_search_agent = build_agent_node("knowledge_search_agent")
access_check_agent     = build_agent_node("access_check_agent")
reasoning_agent        = build_agent_node("reasoning_agent")
action_ticket_agent    = build_agent_node("action_ticket_agent")
    
