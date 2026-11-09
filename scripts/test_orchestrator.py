import sys
import logging
sys.path.append(".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

from core.orchestrator import run_ticket

print("\n" + "="*60)
print("ORCHESTRATOR TESTS")
print("="*60)

# ── Test 1: Bug ticket → knowledge search agent ───────────────
print("\n--- Test 1: Bug ticket---")
result, interrupts = run_ticket(
    initial_message="My mobile app keeps crashing on the analytics screen",
    customer_segment="enterprise",
    sla_plan="enterprise"
)
print(f"Issue Type  : {result.issue_type}")
print(f"Agent Used  : {result.current_agent}")
print(f"Groundedness: {result.groundness_score}")
print(f"HITL Needed : {result.needs_approval}")
print(f"Resolution  :\n{result.resolution}")

# ── Test 2: Access ticket → access check agent ────────────────
print("\n--- Test 2: Access ticket ---")
result2, interrupts2 = run_ticket(
    initial_message="I cannot login, my password is wrong",
    customer_segment="business",
    sla_plan="business",
    customer_id="CUST_001"
)
print(f"Issue Type  : {result2.issue_type}")
print(f"Agent Used  : {result2.current_agent}")
print(f"HITL Needed : {result2.needs_approval}")
print(f"Resolution  :\n{result2.resolution}")

# ── Test 3: Security ticket → reasoning agent + HITL ─────────
print("\n--- Test 3: Security ticket (expect HITL) ---")
result3, interrupts3 = run_ticket(
    initial_message="There are suspicious login attempts from unknown locations",
    customer_segment="enterprise",
    sla_plan="enterprise",
    priority="critical"
)
print(f"Issue Type  : {result3.issue_type}")
print(f"Agent Used  : {result3.current_agent}")
print(f"HITL Needed : {result3.needs_approval}")
print(f"Policy Flags: {result3.policy_flags}")
print(f"Resolution  :\n{result3.resolution}")

if interrupts3:
    print(f"Interrupt   : {interrupts3[0].value}")

print(f"Resolution  :\n{result3.resolution}")

# ── Test 4: Billing ticket → action ticket agent ──────────────
print("\n--- Test 4: Billing ticket ---")
result4, interrupts4  = run_ticket(
    initial_message="I was charged twice for my subscription this month",
    customer_segment="business",
    sla_plan="business",
    customer_id="CUST_002"
)
print(f"Issue Type  : {result4.issue_type}")
print(f"Agent Used  : {result4.current_agent}")
print(f"Ticket      : {result4.tool_results.get('create_ticket', 'not created')}")
print(f"Resolution  :\n{result4.resolution}")

print("\n" + "="*60)
print("ALL ORCHESTRATOR TESTS DONE")
print("="*60)