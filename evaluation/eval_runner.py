# evaluation/eval_runner.py
import json
import logging
from pathlib import Path
from core.orchestrator import run_ticket
from evaluation.session_store import session_store

logger = logging.getLogger(__name__)

BASELINE_PATH = Path("data/eval_baseline.json")


class EvalRunner:
    """
    Batch evaluation runner.

    Runs all 20 panel tickets through the system.
    Scores each against golden resolution_summary.
    Saves baseline scores.
    Detects regression by comparing against baseline.

    Why do we need this?
    → Proves system works with real numbers
    → Catches quality drops after code changes
    → Required for production sign-off with any client
    """

    def __init__(self):
        # Load golden eval set — 20 panel tickets
        with open("data/golden_subset.json") as f:
            self.golden_set = json.load(f)

        # Load router ground truth
        # Maps ticket_id → expected_agent + requires_hitl
        with open("data/router_ground_truth.json") as f:
            self.router_truth = json.load(f)

        logger.info(
            f"EvalRunner ready | "
            f"golden_set={len(self.golden_set)} tickets"
        )

    # ── SCORING METHODS ───────────────────────────────────────

    def score_correctness(
        self,
        generated: str,
        expected: str
    ) -> float:
        """
        Keyword overlap score.

        How many important words from the golden answer
        appear in the generated resolution?

        Why not use LLM for scoring?
        → Costs tokens on every eval run
        → Slower — adds latency to eval
        → Keyword overlap is fast, free, explainable

        In production you would add:
        → ROUGE score (standard NLP metric)
        → Semantic similarity (embedding cosine)
        → LLM-as-judge for edge cases
        """
        if not generated or not expected:
            return 0.0

        # Lowercase and split into word sets
        expected_words  = set(expected.lower().split())
        generated_words = set(generated.lower().split())

        # Remove stop words — they add noise, not signal
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were",
            "to", "of", "and", "in", "for", "you", "your",
            "this", "that", "it", "can", "will", "be",
            "have", "has", "with", "on", "at", "by", "from"
        }
        expected_words  -= stop_words
        generated_words -= stop_words

        if not expected_words:
            return 0.0

        # Overlap = words in both sets
        overlap = expected_words & generated_words
        score   = len(overlap) / len(expected_words)

        return round(score, 3)

    def score_routing(
        self,
        ticket_id: str,
        actual_agent: str
    ) -> tuple[bool, str]:
        """
        Routing accuracy check.

        Did the correct agent handle this ticket?
        Returns (is_correct, expected_agent_name)
        """
        truth = self.router_truth.get(ticket_id, {})
        expected_agent = truth.get("expected_agent", "")

        is_correct = (actual_agent == expected_agent)

        return is_correct, expected_agent

    # ── SINGLE TICKET EVAL ────────────────────────────────────

    def run_single(self, record: dict) -> dict:
        """
        Run one golden ticket through the system.
        Score the result.
        Save to session store.
        Return scored result dict.
        """
        # Run ticket through system
        state, interrupts = run_ticket(
            initial_message=record["initial_message"],
            issue_type=record.get("scenario_key", ""),
            priority=record.get("priority", "medium"),
            customer_segment=record.get(
                "customer_segment", "individual"
            ),
            sla_plan=record.get("sla_plan", "basic"),
            customer_id=record.get("customer_id", "unknown")
        )

        # Score 1 — correctness
        correctness = self.score_correctness(
            generated=state.resolution or "",
            expected=record.get("resolution_summary", "")
        )

        # Score 2 — groundedness
        # Already calculated by reflection_node
        groundedness = state.groundness_score or 0.0

        # Score 3 — routing accuracy
        routing_correct, expected_agent = self.score_routing(
            ticket_id=record["ticket_id"],
            actual_agent=state.current_agent
        )

        # Combined weighted score
        combined = round(
            (correctness    * 0.5) +
            (groundedness   * 0.3) +
            (float(routing_correct) * 0.2),
            3
        )

        # Save score back to state and re-save session
        state.eval_score = combined
        state.expected_resolution = record.get(
            "resolution_summary", ""
        )
        session_store.save(state)

        return {
            "ticket_id":       record["ticket_id"],
            "scenario_key":    record.get("scenario_key", ""),
            "agent_used":      state.current_agent,
            "expected_agent":  expected_agent,
            "routing_correct": routing_correct,
            "correctness":     correctness,
            "groundedness":    groundedness,
            "combined_score":  combined,
            "needs_hitl":      state.needs_approval,
            "interrupted":     len(interrupts) > 0,
            "has_resolution":  bool(state.resolution)
        }

    # ── BATCH EVAL ────────────────────────────────────────────

    def run_batch(self) -> dict:
        """
        Run all 20 golden tickets.
        Aggregate scores.
        Save baseline.
        Return full report.
        """
        logger.info(
            f"EvalRunner batch START | "
            f"tickets={len(self.golden_set)}"
        )

        results = []
        errors  = []

        for i, record in enumerate(self.golden_set):
            logger.info(
                f"Eval {i+1}/{len(self.golden_set)} | "
                f"ticket={record['ticket_id']}"
            )

            try:
                result = self.run_single(record)
                results.append(result)
                print(
                    f"  [{i+1:02d}/{len(self.golden_set)}] "
                    f"{record['ticket_id']} | "
                    f"score={result['combined_score']} | "
                    f"routing={'✅' if result['routing_correct'] else '❌'}"
                )

            except Exception as e:
                logger.error(
                    f"Eval failed | "
                    f"ticket={record['ticket_id']} | "
                    f"error={e}"
                )
                errors.append({
                    "ticket_id": record["ticket_id"],
                    "error":     str(e)
                })
                print(f"  [{i+1:02d}] ❌ FAILED: {e}")

        # ── Aggregate ─────────────────────────────────────────
        if results:
            avg_correctness  = round(
                sum(r["correctness"]   for r in results) / len(results), 3
            )
            avg_groundedness = round(
                sum(r["groundedness"]  for r in results) / len(results), 3
            )
            avg_combined     = round(
                sum(r["combined_score"] for r in results) / len(results), 3
            )
            routing_accuracy = round(
                sum(1 for r in results if r["routing_correct"])
                / len(results), 3
            )
        else:
            avg_correctness = avg_groundedness = \
            avg_combined = routing_accuracy = 0.0

        report = {
            "total_tickets":    len(self.golden_set),
            "completed":        len(results),
            "errors":           len(errors),
            "avg_correctness":  avg_correctness,
            "avg_groundedness": avg_groundedness,
            "avg_combined":     avg_combined,
            "routing_accuracy": routing_accuracy,
            "results":          results,
            "error_details":    errors
        }

        # Save baseline for regression detection
        self._save_baseline(report)

        logger.info(
            f"EvalRunner batch DONE | "
            f"avg_score={avg_combined} | "
            f"routing={routing_accuracy}"
        )

        return report

    # ── BASELINE + REGRESSION ─────────────────────────────────

    def _save_baseline(self, report: dict) -> None:
        """
        Save current scores as baseline.
        Next eval run compares against this.
        """
        baseline = {
            "avg_combined":     report["avg_combined"],
            "avg_correctness":  report["avg_correctness"],
            "avg_groundedness": report["avg_groundedness"],
            "routing_accuracy": report["routing_accuracy"],
            "total_tickets":    report["total_tickets"]
        }

        with open(BASELINE_PATH, "w") as f:
            json.dump(baseline, f, indent=2)

        logger.info(
            f"Baseline saved | "
            f"score={baseline['avg_combined']}"
        )

    def check_regression(self, current_report: dict) -> dict:
        """
        Compare current scores vs saved baseline.
        Flag regression if any metric drops more than 10%.

        Why 10%?
        → Small drops are noise — LLM non-determinism
        → 10% drop is a real signal something broke
        → Tune this threshold per your quality requirements
        """
        if not BASELINE_PATH.exists():
            return {
                "status":      "no_baseline",
                "message":     "Run eval once to create baseline",
                "regressions": []
            }

        with open(BASELINE_PATH) as f:
            baseline = json.load(f)

        regressions = []
        threshold   = 0.10    # 10% drop triggers regression alert

        metrics = [
            "avg_combined",
            "avg_correctness",
            "avg_groundedness",
            "routing_accuracy"
        ]

        for metric in metrics:
            baseline_val = baseline.get(metric, 0)
            current_val  = current_report.get(metric, 0)

            if baseline_val > 0:
                drop = (baseline_val - current_val) / baseline_val

                if drop > threshold:
                    regressions.append({
                        "metric":    metric,
                        "baseline":  baseline_val,
                        "current":   current_val,
                        "drop_pct":  round(drop * 100, 1)
                    })

        return {
            "status":      "regression_found" if regressions else "ok",
            "regressions": regressions
        }


# Single instance
eval_runner = EvalRunner()