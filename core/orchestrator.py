import logging
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from core.state import HelpdeskState, Message
from core.llm_provider import get_llm_fast
from core.agent_registry import ai_registry
from agents import (
    knowledge_search_agent,
    access_check_agent,
    reasoning_agent,
    action_ticket_agent
)
from core.policy_engine import policy_engine
from observability.tracer import span
import time

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# SECTION 1 — PLANNING NODE
#
# First node in the graph.
# Classifies every incoming ticket.
# Sets issue_type, product_area, priority in state.
#
# Uses fast LLM — classification is simple
# temperature=0.0 → deterministic output every time
# ─────────────────────────────────────────────────────────────

PLANNING_PROMPT = ChatPromptTemplate.from_messages([
    (
       "system",
        """You are an IT ticket classifier.
Classify the ticket and return JSON only. No explanation.

Return exactly this JSON structure:
{{
  "issue_type": "<scenario_key>",
  "product_area": "<area>",
  "priority": "<low|medium|high|critical>",
  "routing_decision": "<one line reason for routing>"
}}

issue_type must start with one of:
access, billing, bug, feature, howto, perf, security, other

Examples:
- Login problem → access_bad_password
- App crashing → bug_crash_mobile
- How to export data → howto_export_data
- Charged twice → billing_double_charge
- Slow performance → perf_slow_billing
- Suspicious login → security_suspicious_login""" 
    ),
    (
        "human",
        """Classify this IT support ticket:

        {initial_message}

        Return JSON only."""
    )
])

def planning_node(state: HelpdeskState) -> HelpdeskState:
    """
    Planning Node.
    Classifies incoming ticket.
    sets issue_type, product_area, priority, routing_decision.
    Runs first for every ticket.
    """
    
    with span("node.planning", {
        "session.id": state.session_id,
        "initial_msg": state.initial_message[:100]
    }):
        logger.info(
                f"PlanningNode START | "
                f"session={state.session_id}"
            )
        
        state.messages.append(Message(
            role="system",
            content="Planning node - classifying ticket",
            agent_name="planning_node"
        ))
        
        chain = PLANNING_PROMPT | get_llm_fast() | StrOutputParser()
        
        try:
            raw = chain.invoke({
                "initial_message": state.initial_message
            }) 
            
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            
            clean = clean.strip()
            
            classification = json.loads(clean)
            
            if not state.issue_type:
                state.issue_type = classification.get(
                    "issue_type", "other_unknown"
                )
            if not state.product_area:
                state.product_area = classification.get(
                    "product_area", "unknown"
                )
            if not state.priority:
                state.priority = classification.get(
                    "priority", "medium"
                )
            state.routing_decision = classification.get(
                "routing_decision", ""
            )
            
            logger.info(
                f"PlanningNode DONE | "
                f"issue_type={state.issue_type} | "
                f"priority={state.priority} | "
                f"session={state.session_id}"
            )
        
        except Exception as e:
            logger.error(f"Planning failed: {e} — using defaults")
            if not state.issue_type:
                state.issue_type = "other_unknown"
            if not state.priority:
                state.priority = "medium"
            state.routing_decision = "Planning failed — routed to reasoning agent" 
        
    return state

# ─────────────────────────────────────────────────────────────
# SECTION 2 — ROUTER
#
# This is a CONDITIONAL EDGE — not a node.
# LangGraph calls this function after planning_node.
# Returns the NAME of the next node to run.
#
# Key point: return value must exactly match
# a node name registered in the graph below.
# ─────────────────────────────────────────────────────────────

def router(state: HelpdeskState) -> str:
    """
    Router — conditional edge function.
    Reads state.issue_type.
    Returns name of next node to execute.

    This is NOT a node. It is a routing function.
    LangGraph uses return value to pick next node.
    """
    
    issue_type = state.issue_type or "other_unknown"
    
    agent_def = ai_registry.find_by_scenario(issue_type)
    agent_name = agent_def.name
    
    logger.info(
        f"Router | "
        f"issue_type={issue_type} → "
        f"agent={agent_name} | "
        f"session={state.session_id}"
    )

    return agent_name

# ─────────────────────────────────────────────────────────────
# SECTION 3 — REFLECTION NODE
#
# Runs after every agent.
# Checks quality of resolution.
# Sets groundness_score in state.
#
# Groundedness = how well is the answer
# backed by actual tool results?
# A hallucinated answer has low groundedness.
# ─────────────────────────────────────────────────────────────

REFLECTION_PROMPT = ChatPromptTemplate.from_messages([
    (
       "system",
        """You are a quality checker for IT helpdesk resolutions.
Check if the resolution is grounded and complete.
Return JSON only.

Return exactly:
{{
  "groundness_score": <0.0 to 1.0>,
  "is_complete": <true|false>,
  "feedback": "<one line>"
}}

groundness_score:
1.0 = fully backed by provided context
0.5 = partially backed
0.0 = not backed by context at all""" 
    ),
    (
        "human",
        """Original Issue:
            {issue}

            Agent Resolution:
            {resolution}

            Tool Results Available:
            {tool_results}

            Score the resolution."""
    )
])

def reflection_node(state: HelpdeskState) -> HelpdeskState:
    """
    Reflection Node.
    Checks quality and groundedness of agent resolution.
    Runs after every agent before policy gate.
    """
    with span("node.reflection", {
        "session.id":  state.session_id,
        "agent_used":  state.current_agent
    }):
        logger.info(
            f"ReflectionNode START | "
            f"session={state.session_id}"
        )

        if not state.resolution:
            logger.warning("No resolution to reflect on")
            state.groundness_score = 0.0
            return state
        
        chain = REFLECTION_PROMPT | get_llm_fast() | StrOutputParser()
        
        try:
            raw = chain.invoke({
                "issue": state.initial_message,
                "resolution": state.resolution,
                "tool_results": json.dumps(state.tool_results, indent=2)[:500]
            })
            
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[:4]
            clean = clean.strip()
            
            reflection = json.loads(clean)
            
            state.groundness_score = float(
                reflection.get("groundness_score", 0.5)
            )
            
            logger.info(
                f"ReflectionNode DONE | "
                f"score={state.groundness_score} | "
                f"complete={reflection.get('is_complete')} | "
                f"session={state.session_id}"
            )
            
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            # Default to 0.5 - uncertain not failing
            state.groundness_score = 0.5
        
    return state

# ─────────────────────────────────────────────────────────────
# SECTION 4 — POLICY GATE
#
# Another CONDITIONAL EDGE — not a node.
# Reads state.needs_approval.
# Returns "hitl_node" or END.
#
# This is the last decision point before returning to user.
# ─────────────────────────────────────────────────────────────

def policy_gate(state: HelpdeskState) -> str:
    """
    Policy Gate — conditional edge.
    Runs policy engine against current state.
    Combines agent HITL flags + policy rule evaluation.
    

    Returns:
    "hitl_node" → human approval needed
    END         → auto approved
    """
    
    if state.needs_approval:
        logger.warning(
            f"PolicyGate → HITL required | "
            f"flags={state.policy_flags} | "
            f"session={state.session_id}"
        )
        
        return "hitl_node"
    
    decision = policy_engine.evaluate(state)
    
    if decision.requires_hitl:
        state.needs_approval= True
        state.approval_status= "pending"
        state.policy_flags.append(
            f"policy_rule: {decision.rule_name} | {decision.reason}"
        )
        
    
    logger.info(
        f"PolicyGate → END (no approval needed) | "
        f"rule={decision.rule_name}"
        f"session={state.session_id}"
    )
    
    return END

# ─────────────────────────────────────────────────────────────
# SECTION 5 — HITL NODE
#
# Human In The Loop interrupt.
# Graph PAUSES here and waits for human input.
# Human approves or denies via Streamlit UI.
#
# LangGraph interrupt() pauses execution.
# When human responds, graph resumes from this point.
# ─────────────────────────────────────────────────────────────

def hitl_node(state: HelpdeskState) -> HelpdeskState:
    """
    HITL Node.
    Pauses graph and waits for human approval.
    Graph resumes when human responds.
    """
    
    logger.warning(
        f"HITL INTERRUPT | "
        f"session={state.session_id} | "
        f"flags={state.policy_flags}"
    )
    # interrupt() pauses the graph here
    # Sends context to human via UI
    # Resumes when human sends response
    human_decision = interrupt({
        "message":      "Human approval required",
        "session_id":   state.session_id,
        "resolution":   state.resolution,
        "policy_flags": state.policy_flags,
        "agent_used":   state.current_agent
    })
    
    if human_decision.get("approved"):
        state.approval_status = "approved"
        state.messages.append(Message(
            role="system",
            content=f"Human approved | reason: {human_decision.get('reason', 'approved')}",
            agent_name="hitl_node"
        ))
        logger.info(
            f"HITL APPROVED | session={state.session_id}"
        )
        
    else:
        state.approval_status = "denied"
        state.resolution = (
            f"Action denied by human reviewer.\n"
            f"Reason: {human_decision.get('reason', 'No reason provided')}\n"
            f"Please contact your administrator."
        )
        state.messages.append(Message(
            role="system",
            content=f"Human denied | reason: {human_decision.get('reason', 'denied')}",
            agent_name="hitl_node"
        ))
        logger.warning(
            f"HITL DENIED | session={state.session_id}"
        )
        
    return state

# ─────────────────────────────────────────────────────────────
# SECTION 6 — GRAPH ASSEMBLY
#
# This is where all pieces connect.
# Order matters:
# 1. Create graph with state type
# 2. Add all nodes
# 3. Set entry point
# 4. Add edges (fixed and conditional)
# 5. Compile with checkpointer (enables HITL)
# ─────────────────────────────────────────────────────────────

def build_graph():
    """
    Assembles and compiles the LangGraph StateGraph.
    Called once at startup.
    Returns compiled app ready to run tickets.
    """
    
    graph = StateGraph(HelpdeskState)
    
    graph.add_node("planning_node", planning_node)
    graph.add_node("knowledge_search_agent",    knowledge_search_agent)
    graph.add_node("access_check_agent",        access_check_agent)
    graph.add_node("reasoning_agent",           reasoning_agent)
    graph.add_node("action_ticket_agent",       action_ticket_agent)
    graph.add_node("reflection_node",           reflection_node)
    graph.add_node("hitl_node",                 hitl_node)
    
    graph.set_entry_point("planning_node")
    
    # graph.add_edge("reflection_node", "policy_gate_edge")

    for agent_name in [
        "knowledge_search_agent",
        "access_check_agent",
        "reasoning_agent",
        "action_ticket_agent"
    ]:
        graph.add_edge(agent_name, "reflection_node")
        
    graph.add_edge("hitl_node", END)
        
    graph.add_conditional_edges(
        "planning_node",
        router,
        {
            "knowledge_search_agent": "knowledge_search_agent",
            "access_check_agent":     "access_check_agent",
            "reasoning_agent":        "reasoning_agent",
            "action_ticket_agent":    "action_ticket_agent"
        }
    )
    
    graph.add_conditional_edges(
        "reflection_node",
        policy_gate,
        {
            "hitl_node": "hitl_node",
            END:         END
        }
    )
    
    checkpointer = MemorySaver()
    app = graph.compile(checkpointer=checkpointer)
    
    logger.info("LangGraph StateGraph compiled successfully")
    return app


# ─────────────────────────────────────────────────────────────
# SECTION 7 — HELPER FUNCTION
#
# Clean interface for running one ticket through the graph.
# CLI and Streamlit both call this function.
# Neither needs to know about LangGraph internals.
# ─────────────────────────────────────────────────────────────

# Compile once at import time
app = build_graph()

def run_ticket(
    initial_message: str,
    issue_type: str = "",
    priority: str = "",
    customer_segment: str = "",
    sla_plan: str ="",
    customer_id: str = "",
    product_area: str = ""
) -> tuple[HelpdeskState, list]:
    """
    Main entry point for running one ticket.
    Called by CLI and Streamlit.

    Creates initial state.
    Runs through the full graph.
    Returns final state with resolution.
    """
    #build initial state
    initial_state = HelpdeskState(
        initial_message=initial_message,
        issue_type=issue_type,
        priority=priority,
        customer_segment=customer_segment,
        sla_plan=sla_plan,
        customer_id=customer_id,
        product_area=product_area
    )
    
    config = {
        "configurable": {
            "thread_id": initial_state.session_id
        }
    }
    
    logger.info(
        f"run_ticket START | "
        f"session={initial_state.session_id}"
    )
    
    final_state = app.invoke(
        initial_state,
        config=config
    )
    interrupts = final_state.pop("__interrupt__", [])
    
    state = HelpdeskState(**final_state)
    
    logger.info(
        f"run_ticket DONE | "
        f"agent={final_state.get("current_agent")} | "
        f"hitl={final_state.get('needs_approval')} | "
        f"session={initial_state.session_id}"
    )
    
    return state, interrupts
    
def resume_ticket(
    session_id: str,
    approved: bool,
    reason: str = ""
) -> tuple[HelpdeskState, list]:
    """
    Resume a paused ticket after human decision.

    Called by Streamlit HITL approval buttons.
    Sends human decision back into the graph.
    Graph resumes from hitl_node with the decision.

    Args:
        session_id : the session that was interrupted
        approved   : True = human approved, False = denied
        reason     : human's explanation
    """
    
    config = {
        "configurable": {
            "thread_id": session_id
        }
    }

    # Send human decision back to graph
    # Graph resumes from interrupt() in hitl_node
    human_decision = {
        "approved": approved,
        "reason":   reason or ("Approved by reviewer" if approved else "Denied by reviewer")
    }

    logger.info(
        f"resume_ticket | "
        f"session={session_id} | "
        f"approved={approved}"
    )

    final_state = app.invoke(
        Command(resume=human_decision),
        config=config
    )

    interrupts = final_state.pop("__interrupt__", [])
    state = HelpdeskState(**final_state)

    return state, interrupts