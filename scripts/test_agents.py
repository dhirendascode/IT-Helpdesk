import sys
import logging
sys.path.append(".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

from core.state import HelpdeskState
from agents import (
    knowledge_search_agent,
    access_check_agent,
    reasoning_agent,
    action_ticket_agent
)

print("\n" + "="*60)
print("AGENT TESTS")
print("="*60)

print("\n---- Test 1: Knowledge Search Agent ----")
state1 = HelpdeskState(
    initial_message="My mobile app keeps crashing when I open the analytics dashboard",
    issue_type="bug_crash_mobile",
    product_area="mobile",
    priority="high",
    customer_segment="enterprise",
    sla_plan="enterprise"
)

state1 = knowledge_search_agent(state1)
print(f"Agent     : {state1.current_agent}")
print(f"Error     : {state1.error}")
print(f"KB Results: {len(state1.tool_results.get('knowledge_search', []))}")
print(f"Resolution:\n{state1.resolution}")

# ── Test 2: Access Check Agent ────────────────────────────────
print("\n--- Test 2: Access Check Agent ---")
state2 = HelpdeskState(
    initial_message="I cannot login, my password stopped working suddenly",
    issue_type="access_bad_password",
    product_area="login_auth",
    priority="high",
    customer_segment="enterprise",
    sla_plan="enterprise",
    customer_id="CUST_001"
)
state2 = access_check_agent(state2)
print(f"Agent     : {state2.current_agent}")
print(f"HITL      : {state2.needs_approval}")
print(f"Flags     : {state2.policy_flags}")
print(f"Resolution:\n{state2.resolution}")

# ── Test 3: Reasoning Agent (security) ───────────────────────
print("\n--- Test 3: Reasoning Agent (security) ---")
state3 = HelpdeskState(
    initial_message="I see multiple suspicious login attempts from unknown IP addresses",
    issue_type="security_suspicious_login",
    product_area="login_auth",
    priority="critical",
    customer_segment="enterprise",
    sla_plan="enterprise"
)
state3 = reasoning_agent(state3)
print(f"Agent     : {state3.current_agent}")
print(f"HITL      : {state3.needs_approval}")
print(f"Flags     : {state3.policy_flags}")
print(f"Resolution:\n{state3.resolution}")

# ── Test 4: Action Ticket Agent ───────────────────────────────
print("\n--- Test 4: Action Ticket Agent ---")
state4 = HelpdeskState(
    initial_message="I was charged twice for my subscription this month",
    issue_type="billing_double_charge",
    product_area="billing",
    priority="high",
    customer_segment="business",
    sla_plan="business",
    customer_id="CUST_002"
)
state4 = action_ticket_agent(state4)
print(f"Agent     : {state4.current_agent}")
print(f"Ticket    : {state4.tool_results.get('create_ticket', 'not created')}")
print(f"Resolution:\n{state4.resolution}")

print("\n" + "="*60)
print("ALL AGENT TESTS DONE")
print("="*60)