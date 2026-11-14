# scripts/run_eval.py
import sys
import logging
sys.path.append(".")

# Suppress verbose logs during eval
logging.basicConfig(level=logging.WARNING)

from evaluation.eval_runner import eval_runner

print("="*60)
print("EVAL RUNNER")
print(f"Running {len(eval_runner.golden_set)} golden tickets")
print("="*60 + "\n")

# Run full batch
report = eval_runner.run_batch()

# Print summary
print("\n" + "="*60)
print("RESULTS")
print("="*60)
print(f"Completed      : {report['completed']}/{report['total_tickets']}")
print(f"Errors         : {report['errors']}")
print(f"Combined Score : {report['avg_combined']}")
print(f"Correctness    : {report['avg_correctness']}")
print(f"Groundedness   : {report['avg_groundedness']}")
print(f"Routing        : {report['routing_accuracy']}")

# Check regression
print("\n--- Regression Check ---")
regression = eval_runner.check_regression(report)

if regression["status"] == "ok":
    print("✅ No regression detected")
elif regression["status"] == "no_baseline":
    print("ℹ️  Baseline created — run again to detect regression")
else:
    print("❌ Regression detected!")
    for r in regression["regressions"]:
        print(
            f"  {r['metric']} dropped {r['drop_pct']}% "
            f"({r['baseline']} → {r['current']})"
        )

# Show per-ticket routing accuracy
print("\n--- Routing Breakdown ---")
correct   = sum(1 for r in report["results"] if r["routing_correct"])
incorrect = [r for r in report["results"] if not r["routing_correct"]]

print(f"Correct routing: {correct}/{report['completed']}")

if incorrect:
    print("Wrong routing:")
    for r in incorrect:
        print(
            f"  {r['ticket_id']} | "
            f"expected={r['expected_agent']} | "
            f"got={r['agent_used']}"
        )

print("\n" + "="*60)
print("EVAL DONE")
print("="*60)