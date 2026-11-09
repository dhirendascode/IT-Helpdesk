# core/tool_implementations.py
import uuid
import logging
from vector_store.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# RULE FOR ALL IMPLEMENTATIONS
#
# Every function:
# → Takes dict as input
# → Returns dict as output
# → Never touches HelpdeskState directly
# → Never calls tool_registry (no circular calls)
# → Raises exception on failure (registry catches it)
# ─────────────────────────────────────────────────────────────

def knowledge_search(params: dict) -> dict:
    """
    Search vector DB for similar past tickets.
    This is the RAG retrieval step.

    In production: same code, real data in vector DB
    """
    query = params.get("query", "")
    top_k = params.get("top_k", 3)

    if not query:
        raise ValueError("knowledge_search requires 'query' parameter")

    store = get_vector_store()
    results = store.similarity_search_with_score(query, k=top_k)

    formatted = []
    for doc, score in results:
        formatted.append({
            "ticket_id":          doc.metadata.get("ticket_id", "unknown"),
            "scenario_key":       doc.metadata.get("scenario_key", "unknown"),
            "resolution_summary": doc.metadata.get("resolution_summary", ""),
            "similarity_score":   round(float(score), 3),
            "content":            doc.page_content[:300]
        })

    logger.info(
        f"knowledge_search | query='{query[:50]}' | "
        f"results={len(formatted)}"
    )

    return {
        "results":     formatted,
        "total_found": len(formatted)
    }


def get_account_status(params: dict) -> dict:
    """
    Mock account and SLA status lookup.

    In production: replace body with CRM API call
    Function signature stays the same — registry never changes
    """
    customer_id = params.get("customer_id", "unknown")
    sla_plan    = params.get("sla_plan", "basic")

    # Mock SLA configuration
    sla_config = {
        "enterprise": {
            "priority_support": True,
            "sla_hours":        4,
            "account_status":   "active"
        },
        "business": {
            "priority_support": True,
            "sla_hours":        8,
            "account_status":   "active"
        },
        "basic": {
            "priority_support": False,
            "sla_hours":        24,
            "account_status":   "active"
        }
    }

    config = sla_config.get(sla_plan, sla_config["basic"])

    return {
        "customer_id":      customer_id,
        "account_status":   config["account_status"],
        "sla_tier":         sla_plan,
        "priority_support": config["priority_support"],
        "sla_hours":        config["sla_hours"]
    }


def check_policy(params: dict) -> dict:
    """
    Mock policy engine.

    In production: replace with OPA (Open Policy Agent)
    or custom policy rules from policy_engine.py

    Rules:
    → Any security action requires HITL
    → Any access grant requires HITL
    → Everything else is auto-approved
    """
    action           = params.get("action", "")
    customer_segment = params.get("customer_segment", "individual")
    priority         = params.get("priority", "medium")

    # Actions that always require human approval
    high_risk_actions = [
        "grant_access",
        "flag_security_incident",
        "security_suspicious_login",
        "security_compliance",
        "security_vuln_login"
    ]

    requires_hitl = any(
        risk in action.lower()
        for risk in high_risk_actions
    )

    return {
        "allowed":       True,
        "requires_hitl": requires_hitl,
        "reason": (
            f"Action '{action}' requires human approval due to security policy"
            if requires_hitl
            else f"Action '{action}' is permitted for {customer_segment}"
        )
    }


def create_ticket(params: dict) -> dict:
    """
    Mock ticket creation.

    In production: replace with ServiceNow / Jira / Zendesk API call
    Returns a mock ticket ID in same format as real dataset
    """
    ticket_id = f"TCKT_{uuid.uuid4().hex[:6].upper()}"

    logger.info(f"Ticket created: {ticket_id}")

    return {
        "ticket_id":     ticket_id,
        "status":        "open",
        "issue_summary": params.get("issue_summary", ""),
        "priority":      params.get("priority", "medium"),
        "customer_id":   params.get("customer_id", "unknown"),
        "created_at":    "2024-01-01T00:00:00Z"
    }


def grant_access(params: dict) -> dict:
    """
    Mock access grant.

    NOTE: This function should NEVER auto-execute.
    approval_required=true in tools.yaml means
    tool_registry.execute() returns before reaching here.

    This implementation exists only for:
    → Post-approval execution (after human approves)
    → Testing purposes

    In production: replace with IAM API (Okta, Active Directory)
    """
    logger.warning(
        "grant_access executing — ensure HITL approval was obtained"
    )

    return {
        "status":       "granted",
        "granted_by":   "human_approver",
        "customer_id":  params.get("customer_id", "unknown"),
        "system":       params.get("system", "unknown"),
        "access_level": params.get("access_level", "read")
    }


def reset_password(params: dict) -> dict:
    """
    Mock password reset trigger.

    In production: replace with Auth0 / Okta API call
    """
    return {
        "status":          "reset_initiated",
        "reset_link_sent": True,
        "method":          params.get("method", "email"),
        "customer_id":     params.get("customer_id", "unknown"),
        "expires_in":      "24 hours"
    }


def flag_security_incident(params: dict) -> dict:
    """
    Mock security incident flag.

    NOTE: Like grant_access — approval_required=true in tools.yaml
    Registry intercepts before reaching here in normal flow.

    In production: replace with SIEM API (Splunk, PagerDuty)
    """
    incident_id = f"INC_{uuid.uuid4().hex[:6].upper()}"

    logger.warning(
        f"Security incident flagged: {incident_id} | "
        f"type={params.get('incident_type')} | "
        f"severity={params.get('severity')}"
    )

    return {
        "incident_id":  incident_id,
        "status":       "flagged",
        "escalated_to": "security_team",
        "severity":     params.get("severity", "medium"),
        "ticket_id":    params.get("ticket_id", "unknown")
    }


# ─────────────────────────────────────────────────────────────
# TOOL IMPLEMENTATIONS MAP
#
# This dict connects tool names (from tools.yaml)
# to their implementation functions (above)
#
# tool_registry.py imports TOOL_IMPLEMENTATIONS
# and uses it to find the right function to call
#
# Adding a new tool:
# Step 1 → write the function above
# Step 2 → add entry to tools.yaml
# Step 3 → add to this map
# That is ALL — no other file changes needed
# ─────────────────────────────────────────────────────────────

TOOL_IMPLEMENTATIONS = {
    "knowledge_search":       knowledge_search,
    "get_account_status":     get_account_status,
    "check_policy":           check_policy,
    "create_ticket":          create_ticket,
    "grant_access":           grant_access,
    "reset_password":         reset_password,
    "flag_security_incident": flag_security_incident,
}