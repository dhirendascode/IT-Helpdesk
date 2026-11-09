# scripts/test_ai_registry.py
import sys
sys.path.append(".")

from core.agent_registry import ai_registry

print("=== AGENT REGISTRY TEST ===\n")

# ── Test 1: Full summary ──────────────────────────────────────
print(ai_registry.summary())

# ── Test 2: Routing by scenario key ──────────────────────────
print("--- Routing Test ---")
test_scenarios = [
    "access_bad_password",
    "billing_double_charge",
    "bug_crash_mobile",
    "feature_advanced_login",
    "howto_setup_api",
    "perf_slow_billing",
    "security_suspicious_login",
    "other_unsure_category",
    "unknown_something_new"        # tests fallback
]

for scenario in test_scenarios:
    agent = ai_registry.find_by_scenario(scenario)
    hitl  = "⚠️  HITL" if agent.requires_hitl else "✅ Auto"
    print(f"  {scenario:<35} → {agent.name} {hitl}")

# ── Test 3: Capability lookup ─────────────────────────────────
print("\n--- Capability Test ---")
for cap in ["semantic_search", "policy_check", "billing_resolution"]:
    agents = ai_registry.find_by_capability(cap)
    print(f"  {cap:<25} → {[a.name for a in agents]}")

# ── Test 4: HITL flags ────────────────────────────────────────
print("\n--- HITL Test ---")
for name in ai_registry.agents:
    flag = "⚠️  YES" if ai_registry.requires_hitl(name) else "✅ NO"
    print(f"  {name:<30} → HITL: {flag}")

print("\n=== ALL TESTS DONE ===")