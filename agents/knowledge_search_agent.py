import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.llm_provider import get_llm, get_llm_fast
from core.tool_registry import tool_registry
from core.schemas import ToolCallRequest
from core.state import HelpdeskState, Message


logger = logging.getLogger(__name__)

# PROMPT TEMPLATE

#Two parts:
# system -> tells LLM its role and rules (never changes)
# human -> the actual task with variables (filled at runtime)

# Variables in {curly_braces} -> filled by chain.invoke({})

PROMPT = ChatPromptTemplate([
    (
        "system",
        """You are a senior IT helpdesk specialist.
Your job is to resolve IT support tickets using past resolutions as reference.

Rules:
- Base your resolution ONLY on the past resolutions provided
- Be specific and actionable — give exact numbered steps
- If past resolutions are not relevant say: "No similar past resolution found. Escalating."
- Keep response under 200 words
- Never invent steps not supported by the context provided"""
        
    ),
    (
        "human",
        """User Issue:
{issue}

Similar Past Resolutions Found:
{context}

Product Area : {product_area}
Priority     : {priority}

Provide a clear step by step resolution for this issue."""
    )
    
])

#__________________________________________________________

# AGENT FUNCTION

#LangGraph rule:
# Every node is a funtion that takes state and return state
# Input -> HelpdeskState
# Output -> HelpdeskState (updated)

# Never return a new state object
# Always modify and return the same state

# _________________________________________________________


def knowledge_search_agent(state: HelpdeskState) -> HelpdeskState:
    """
    Knowledge Search Agent.
    Handles: bug, feature, howto tickets.
    Pattern: RAG - retrieve past resolution + generate answer.
    """
    logger.info(
        f"KnowledgeSearchAgent START | "
        f"session={state.session_id}"
    )
    
    state.current_agent = "knowledge_search_agent"
    
    state.messages.append(Message(
        role="system",
        content="Knowledge Search Agent activated",
        agent_name="knowledge_search_agent"
    ))
    
    search_result = tool_registry.execute(ToolCallRequest(
        tool_name="knowledge_search",
        parameters={
            "query": state.initial_message,
            "top_k": 3
        },
        agent_name="knowledge_search_agent",
        session_id=state.session_id
    ))
    
    if not search_result.success:
        logger.warning(
            f"Knowledge search failed: {search_result.error}"
        )
        state.error = search_result.error
        state.resolution = (
            "Unable to search knowledge base."
            "Please escalate to a human agent."
        )
        
        return state
    
    results = search_result.result.get("results",[])
    
    state.tool_results["knowledge_search"] = results
    
    if not results:
        context = "No similar past resolutions found in Knowledge base."
    else:
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"Past Resolution {i}:\n"
                f"Scenario: {r.get('scenario_key', 'unknown')}\n"
                f"Similarity: {r.get('similarity_score', 0):.2f}\n"
                f"Resolution: {r.get('resolution_summary', 'N/A')}"
            )
        context = "\n\n".join(context_parts)
        
    chain = PROMPT | get_llm() | StrOutputParser()
    
    try:
        resolution = chain.invoke({
            "issue": state.initial_message,
            "context": context,
            "product_area": state.product_area or "unknown",
            "priority": state.priority or "medium"
        })
        
        state.resolution = resolution
        state.messages.append(Message(
            role="agent",
            content=resolution,
            agent_name="knowledge_search_agent"
        ))
        
        logger.info(
            f"KnowledgeSearchAgent DONE | "
            f"results_used={len(results)} | "
            f"session={state.session_id}"
        )
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        state.error = str(e)
        state.resolution = "Resolution generation failed. Please retry."
        
    return state
        
    