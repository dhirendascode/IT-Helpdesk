# scripts/test_session_store.py
import sys
sys.path.append(".")

from core.orchestrator import run_ticket
from evaluation.session_store import session_store

print("="*60)
print("SESSION STORE TEST")
print("="*60)

# ── Test 1: Run ticket and verify it saves ────────────────────
print("\n--- Test 1: Run ticket and save ---")
state, _ = run_ticket(
    initial_message="App keeps crashing on mobile analytics screen",
    priority="high",
    customer_segment="enterprise",
    sla_plan="enterprise"
)
session_id = state.session_id
print(f"Session ID : {session_id}")
print(f"Agent      : {state.current_agent}")
print(f"Saved      : checking...")

# ── Test 2: Load the saved session ───────────────────────────
print("\n--- Test 2: Load saved session ---")
loaded = session_store.load(session_id)
if loaded:
    print(f"Loaded     : ✅")
    print(f"Session ID : {loaded.session_id}")
    print(f"Agent      : {loaded.current_agent}")
    print(f"Issue Type : {loaded.issue_type}")
    print(f"Resolution : {loaded.resolution[:80]}...")
else:
    print("Load failed ❌")

# ── Test 3: List all sessions ─────────────────────────────────
print("\n--- Test 3: List sessions ---")
sessions = session_store.list_sessions()
print(f"Total sessions saved: {len(sessions)}")
for s in sessions[:3]:    # show first 3
    print(
        f"  {s['session_id'][:8]}... | "
        f"{s['issue_type']} | "
        f"{s['agent_used']} | "
        f"score={s['eval_score']}"
    )

# ── Test 4: Replay session ────────────────────────────────────
print("\n--- Test 4: Replay session ---")
replayed = session_store.replay(session_id)
if replayed:
    print(f"Replay     : ✅")
    print(f"Same agent : {replayed.current_agent == state.current_agent}")
    print(f"Agent      : {replayed.current_agent}")
else:
    print("Replay failed ❌")

print("\n" + "="*60)
print("SESSION STORE TESTS DONE")
print("="*60)