# scripts/test_policy_engine.py
import sys
sys.path.append(".")

from core.policy_engine import policy_engine
from core.state import HelpdeskState

print("="*60)
print("POLICY ENGINE TESTS")
print("="*60)

tests = [
    {
        "name": "Security ticket → must be HITL",
        "state": HelpdeskState(
            initial_message="suspicious login",
            issue_type="security_suspicious_login",
            priority="high",
            customer_segment="enterprise"
        ),
        "expect_hitl": True
    },
    {
        "name": "Critical priority → must be HITL",
        "state": HelpdeskState(
            initial_message="app down",
            issue_type="perf_degraded",
            priority="critical",
            customer_segment="business"
        ),
        "expect_hitl": True
    },
    {
        "name": "Bug ticket low priority → no HITL",
        "state": HelpdeskState(
            initial_message="minor bug",
            issue_type="bug_crash_mobile",
            priority="low",
            customer_segment="individual"
        ),
        "expect_hitl": False
    },
    {
        "name": "Billing ticket → no HITL",
        "state": HelpdeskState(
            initial_message="double charge",
            issue_type="billing_double_charge",
            priority="medium",
            customer_segment="business"
        ),
        "expect_hitl": False
    },
    {
        "name": "Access high priority enterprise → HITL",
        "state": HelpdeskState(
            initial_message="cannot login",
            issue_type="access_bad_password",
            priority="high",
            customer_segment="enterprise"
        ),
        "expect_hitl": True
    },
    {
        "name": "Howto ticket → no HITL",
        "state": HelpdeskState(
            initial_message="how to export",
            issue_type="howto_export_data",
            priority="low",
            customer_segment="individual"
        ),
        "expect_hitl": False
    }
]

print()
all_passed = True

for test in tests:
    decision = policy_engine.evaluate(test["state"])
    passed = decision.requires_hitl == test["expect_hitl"]
    all_passed = all_passed and passed

    status = "✅ PASS" if passed else "❌ FAIL"
    hitl   = "HITL" if decision.requires_hitl else "AUTO"

    print(f"{status} | {hitl} | rule={decision.rule_name}")
    print(f"       {test['name']}")
    print(f"       reason: {decision.reason}")
    print()

print("="*60)
print(f"RESULT: {'ALL PASSED ✅' if all_passed else 'SOME FAILED ❌'}")
print("="*60)