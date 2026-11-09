import yaml
import logging
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from core.state import HelpdeskState

logger = logging.getLogger(__name__)

class PolicyRule(BaseModel):
    """One rule from policy_rules.yaml"""
    model_config = ConfigDict(extra="forbid")
    
    name: str
    description: str
    conditions: dict
    action: str
    reason: str
    priority: int
    

class PolicyDecision(BaseModel):
    """
    Result of policy evaluation.
    Returned by policy_engine.evaluate()
    """
    model_config = ConfigDict(extra="forbid")
    
    requires_hitl: bool
    reason: str
    rule_name: str
    

class PolicyEngine:
    """
    Evaluates policy rules against ticket state.
    Decides if human approval is required.

    Rules loaded from registry/policy_rules.yaml.
    Rules evaluated in priority order — first match wins.
    """
    
    def __init__(
        self,
        yaml_path: str = "registry/policy_rules.yaml"
    ):
        self.rules: list[PolicyRule] = []
        self._load_rules(yaml_path)
        logger.info(
            f"PolicyEngine ready | "
            f"{len(self.rules)} rules loaded"
        )
        
    def _load_rules(self, yaml_path: str) -> None:
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Policy rules not found: {yaml_path}"
            )
        
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file)
            
        rules = [PolicyRule(**r) for r in data["rules"]]
        
        self.rules = sorted(rules, key=lambda r: r.priority)
        
    def evaluate(self, state: HelpdeskState) -> PolicyDecision:
        """
        Main method.
        Evaluates all rules against current state.
        Returns first matching rule's decision.

        Always returns a decision — never raises exception.
        Default fallback is allow if no rules match.
        """
        logger.info(
            f"PolicyEngine evaluating | "
            f"issue_type={state.issue_type} | "
            f"priority={state.priority} | "
            f"segment={state.customer_segment}"
        )
        
        for rule in self.rules:
            if self._matches(rule, state):
                decision = PolicyDecision(
                    requires_hitl=(rule.action == "require_hitl"),
                    reason=rule.reason,
                    rule_name=rule.name
                )
                
                logger.info(
                    f"PolicyEngine match | "
                    f"rule={rule.name} | "
                    f"hitl={decision.requires_hitl}"
                )
                
                return decision
            
        return PolicyDecision(
            requires_hitl=False,
            reason="No matching rule - defaulting to allow",
            rule_name="fallback_allow"
        )
    
    def _matches(
        self,
        rule: PolicyRule,
        state: HelpdeskState
    ) -> bool:
        """
        Checks if a rule applies to this state.
        ALL conditions must match for rule to fire.
        Empty conditions {} matches everything.
        """
        
        conditions = rule.conditions
        
        if not conditions:
            return True
        
        if "issue_type_prefix" in conditions:
            prefix = conditions["issue_type_prefix"]
            issue_prefix = (state.issue_type or "").split("_")[0]
            if issue_prefix != prefix:
                return False
            
        if "priority" in conditions:
            allowed_priorities = conditions["priority"]
            if state.priority not in allowed_priorities:
                return False
            
        # ── Check customer_segment ────────────────────────────
        if "customer_segment" in conditions:
            allowed_segments = conditions["customer_segment"]
            if state.customer_segment not in allowed_segments:
                return False
            
        return True
    

policy_engine = PolicyEngine()
    