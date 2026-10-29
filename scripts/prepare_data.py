import pandas as pd
import json
from pathlib import Path

def prepare_data():
    df = pd.read_csv("data/golden_it_support_tickets.csv")
    
    columns_to_keep = [
        "ticket_id",
        "initial_message",
        "resolution_summary",
        "agent_first_reply",
        "issue_type",
        "product_area",
        "priority",
        "customer_segment",
        "sla_plan",
        "scenario_key",
        "status",
        "customer_sentiment",
        "csat_score",
        "eval_split"
    ]
    
    df = df[columns_to_keep].copy()
    
     # --- SPLIT 1: KNOWLEDGE BASE (extended) ---
    # These go into the vector DB
    # Agent retrieves from these during inference
    
    kb = df[df["eval_split"]=="extended"].copy()
    kb_records = kb.to_dict(orient = "records")
    
    kb_path = Path("data/golden_it_support_tickets.json")
    
    kb_path.parent.mkdir(exist_ok=True)
    with open(kb_path, "w") as file:
        json.dump(kb_records, file, indent=2)
        
    print(f"Knowledge Base: {len(kb_records)} records → {kb_path}")
    
    # --- SPLIT 2: EVAL SET (panel) ---
    # These are frozen test cases
    # Never seeded into vector DB
    # Used only by eval_runner.py
    eval_set = df[df["eval_split"] == "panel"].copy()
    eval_records = eval_set.to_dict(orient="records")

    eval_path = Path("data/golden_subset.json")
    with open(eval_path, "w") as f:
        json.dump(eval_records, f, indent=2)

    print(f"Eval Set:       {len(eval_records)} records → {eval_path}")
    
      # --- SPLIT 3: ROUTER MAP ---
    # Extract prefix from scenario_key
    # Used to validate router accuracy in eval
    router_map = {}
    prefix_to_agent = {
        "access":   "access_check_agent",
        "billing":  "action_ticket_agent",
        "bug":      "knowledge_search_agent",
        "feature":  "knowledge_search_agent",
        "howto":    "knowledge_search_agent",
        "perf":     "reasoning_agent",
        "security": "reasoning_agent",
        "other":    "reasoning_agent"
    }

    for record in eval_records:
        prefix = record["scenario_key"].split("_")[0]
        router_map[record["ticket_id"]] = {
            "scenario_key": record["scenario_key"],
            "expected_agent": prefix_to_agent.get(prefix, "reasoning_agent"),
            "requires_hitl": prefix == "security"
        }

    router_path = Path("data/router_ground_truth.json")
    with open(router_path, "w") as f:
        json.dump(router_map, f, indent=2)

    print(f"Router Map:     {len(router_map)} entries → {router_path}")
    
     # --- SUMMARY ---
    print("\n=== SCENARIO COVERAGE ===")
    for prefix, agent in prefix_to_agent.items():
        panel_count = sum(
            1 for r in eval_records
            if r["scenario_key"].startswith(prefix)
        )
        kb_count = sum(
            1 for r in kb_records
            if r["scenario_key"].startswith(prefix)
        )
        hitl = " ← HITL" if prefix == "security" else ""
        print(f"  {prefix:<10} KB:{kb_count}  EVAL:{panel_count}  →  {agent}{hitl}")

if __name__ == "__main__":
    prepare_data()
    
    