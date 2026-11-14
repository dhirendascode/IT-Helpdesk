# scripts/test_observability.py
import sys
sys.path.append(".")

# Set to console so we see spans in terminal
import os
os.environ["OTEL_EXPORT"] = "console"

from core.orchestrator import run_ticket

print("="*60)
print("OBSERVABILITY TEST")
print("Running one ticket — watch for OTEL spans below")
print("="*60 + "\n")

state, interrupts = run_ticket(
    initial_message="My mobile app keeps crashing on analytics",
    priority="high",
    customer_segment="enterprise",
    sla_plan="enterprise"
)

print("\n" + "="*60)
print("TICKET RESULT")
print("="*60)
print(f"Session  : {state.session_id}")
print(f"Agent    : {state.current_agent}")
print(f"Issue    : {state.issue_type}")
print(f"Score    : {state.groundness_score}")
print(f"HITL     : {state.needs_approval}")
print(f"\nResolution:\n{state.resolution}")