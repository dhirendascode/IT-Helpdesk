# evaluation/session_store.py
import json
import logging
from pathlib import Path
from datetime import datetime
from core.state import HelpdeskState

logger = logging.getLogger(__name__)

SESSION_DIR = Path("data/sessions")


class SessionStore:
    """
    Saves and loads full ticket run sessions to disk.

    Why JSON files and not a database?
    → Simple. No setup needed.
    → Human readable — open any file and read it
    → Easy to share for debugging
    → In production: replace with PostgreSQL or Redis
    """

    def __init__(self):
        # Create sessions directory if it does not exist
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"SessionStore ready | dir={SESSION_DIR}")

    def save(self, state: HelpdeskState) -> str:
        """
        Save a completed ticket run.
        Called automatically by orchestrator after every run.
        Returns path of saved file.
        """
        session_data = {
            "saved_at":  datetime.utcnow().isoformat(),
            "session_id": state.session_id,
            "state":     state.model_dump()
        }

        path = SESSION_DIR / f"{state.session_id}.json"

        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"Session saved | session={state.session_id}")
        return str(path)

    def load(self, session_id: str) -> HelpdeskState | None:
        """
        Load a saved session by session_id.
        Returns HelpdeskState or None if not found.
        """
        path = SESSION_DIR / f"{session_id}.json"

        if not path.exists():
            logger.warning(f"Session not found: {session_id}")
            return None

        with open(path) as f:
            data = json.load(f)

        state = HelpdeskState(**data["state"])
        logger.info(f"Session loaded | session={session_id}")
        return state

    def list_sessions(self) -> list[dict]:
        """
        List all saved sessions — summary only.
        Not full state — just what dashboard needs to display.
        """
        sessions = []

        for path in sorted(
            SESSION_DIR.glob("*.json"),
            reverse=True    # newest first
        ):
            with open(path) as f:
                data = json.load(f)

            state_data = data.get("state", {})
            sessions.append({
                "session_id":     data["session_id"],
                "saved_at":       data["saved_at"],
                "issue_type":     state_data.get("issue_type", ""),
                "agent_used":     state_data.get("current_agent", ""),
                "needs_approval": state_data.get("needs_approval", False),
                "has_resolution": bool(state_data.get("resolution")),
                "eval_score":     state_data.get("eval_score")
            })

        return sessions

    def replay(self, session_id: str) -> HelpdeskState | None:
        """
        Replay a saved session.
        Re-runs the ticket with same inputs through orchestrator.
        Useful for regression testing and debugging.
        """
        saved_state = self.load(session_id)
        if not saved_state:
            return None

        logger.info(f"Replaying session | session={session_id}")

        # Import here to avoid circular import
        # orchestrator imports session_store
        # session_store cannot import orchestrator at top level
        from core.orchestrator import run_ticket

        replayed_state, _ = run_ticket(
            initial_message=saved_state.initial_message,
            issue_type=saved_state.issue_type,
            priority=saved_state.priority,
            customer_segment=saved_state.customer_segment,
            sla_plan=saved_state.sla_plan,
            customer_id=saved_state.customer_id,
            product_area=saved_state.product_area
        )

        return replayed_state


# Single instance
session_store = SessionStore()