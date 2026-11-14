# api/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import sys
sys.path.append(".")

from config import settings


from core.orchestrator import run_ticket, resume_ticket
from core.agent_registry import ai_registry
from core.tool_registry import tool_registry
from evaluation.session_store import session_store
from evaluation.eval_runner import eval_runner

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IT Helpdesk Agent API",
    description=(
        "Multi-agent IT helpdesk system built with "
        "LangGraph, Groq, and OpenTelemetry. "
        "Supports HITL, eval, and session replay."
    ),
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Models ────────────────────────────────────────────────────

class TicketRequest(BaseModel):
    initial_message:  str
    priority:         str = "medium"
    customer_segment: str = "individual"
    sla_plan:         str = "standard"
    customer_id:      str = ""
    issue_type:       str = ""
    product_area:     str = ""

    model_config = {
        "json_schema_extra": {
            "example": {
                "initial_message":  "My mobile app keeps crashing",
                "priority":         "high",
                "customer_segment": "enterprise",
                "sla_plan":         "enterprise",
                "customer_id":      "CUST_001"
            }
        }
    }

class TicketResponse(BaseModel):
    session_id:         str
    issue_type:         str
    agent_used:         str
    resolution:         str | None
    needs_approval:     bool
    approval_status:    str
    groundness_score: float | None
    policy_flags:       list[str]
    interrupted:        bool

class ApprovalRequest(BaseModel):
    approved: bool
    reason:   str = ""

class EvalResponse(BaseModel):
    total_tickets:    int
    completed:        int
    errors:           int
    avg_combined:     float
    avg_correctness:  float
    avg_groundedness: float
    routing_accuracy: float

# ── Health ────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Health check — use this to verify API is running."""
    return {
        "status":  "ok",
        "service": "it-helpdesk-agent",
        "version": "1.0.0"
    }

# ── Tickets ───────────────────────────────────────────────────

@app.post(
    "/api/v1/ticket",
    response_model=TicketResponse,
    tags=["Tickets"]
)
def process_ticket(request: TicketRequest):
    """
    Submit an IT support ticket.

    Flow:
    1. Planning node classifies the ticket
    2. Router sends to correct agent
    3. Agent searches KB and generates resolution
    4. Policy engine checks if HITL needed
    5. Returns resolution or pending approval status

    If needs_approval=true — call /approve endpoint next.
    """
    try:
        state, interrupts = run_ticket(
            initial_message=request.initial_message,
            priority=request.priority,
            customer_segment=request.customer_segment,
            sla_plan=request.sla_plan,
            customer_id=request.customer_id,
            issue_type=request.issue_type,
            product_area=request.product_area
        )

        return TicketResponse(
            session_id=state.session_id,
            issue_type=state.issue_type,
            agent_used=state.current_agent,
            resolution=state.resolution,
            needs_approval=state.needs_approval,
            approval_status=state.approval_status,
            groundness_score=state.groundness_score,
            policy_flags=state.policy_flags,
            interrupted=len(interrupts) > 0
        )

    except Exception as e:
        logger.error(f"Ticket failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/v1/ticket/{session_id}",
    tags=["Tickets"]
)
def get_ticket(session_id: str):
    """Get saved ticket state by session ID."""
    state = session_store.load(session_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found"
        )
    return state.model_dump()


@app.post(
    "/api/v1/ticket/{session_id}/approve",
    tags=["HITL"]
)
def approve_ticket(session_id: str, request: ApprovalRequest):
    """
    Approve or deny a ticket pending human review.
    Resumes the LangGraph graph with human decision.
    """
    try:
        state, _ = resume_ticket(
            session_id=session_id,
            approved=request.approved,
            reason=request.reason
        )

        return {
            "session_id":      session_id,
            "approved":        request.approved,
            "approval_status": state.approval_status,
            "resolution":      state.resolution
        }

    except Exception as e:
        logger.error(f"Approval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Sessions ──────────────────────────────────────────────────

@app.get("/api/v1/sessions", tags=["Sessions"])
def list_sessions(limit: int = 50):
    """List all saved ticket sessions. Newest first."""
    sessions = session_store.list_sessions()
    return {
        "total":    len(sessions),
        "sessions": sessions[:limit]
    }

# ── Registry ──────────────────────────────────────────────────

@app.get("/api/v1/agents", tags=["Registry"])
def list_agents():
    """List all registered agents."""
    return {
        "agents": [
            a.model_dump() for a in ai_registry.list_agents()
        ]
    }


@app.get("/api/v1/tools", tags=["Registry"])
def list_tools():
    """List all available tools."""
    return {
        "tools": [
            t.model_dump() for t in tool_registry.list_tools()
        ]
    }

# ── Eval ──────────────────────────────────────────────────────

@app.post(
    "/api/v1/eval/run",
    response_model=EvalResponse,
    tags=["Evaluation"]
)
def run_evaluation():
    """
    Run full batch evaluation against 20 golden tickets.
    Takes 2-3 minutes. Saves baseline after completion.
    """
    try:
        report = eval_runner.run_batch()
        return EvalResponse(
            total_tickets=report["total_tickets"],
            completed=report["completed"],
            errors=report["errors"],
            avg_combined=report["avg_combined"],
            avg_correctness=report["avg_correctness"],
            avg_groundedness=report["avg_groundedness"],
            routing_accuracy=report["routing_accuracy"]
        )
    except Exception as e:
        logger.error(f"Eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/eval/baseline", tags=["Evaluation"])
def get_baseline():
    """Get saved eval baseline scores."""
    from pathlib import Path
    import json

    path = Path("data/eval_baseline.json")
    if not path.exists():
        return {
            "status":  "no_baseline",
            "message": "Run /eval/run first"
        }

    with open(path) as f:
        return json.load(f)