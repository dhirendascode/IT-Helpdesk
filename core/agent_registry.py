import json
import logging
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AgentDefinition(BaseModel):
    name: str
    version: str
    description: str
    capabilities: list[str]
    handles_scenarios: list[str]
    tools_used: list[str]
    requires_hitl: bool
    enabled: bool
    
class AIRegistry:
    def __init__(self, json_path: str = "registry/agents.json"):
        self.agents: dict[str, AgentDefinition] = {}
        self._load(json_path)
        logger.info(f"AI Registry loaded {len(self.agents)} agents")
        
    def _load(self, json_path: str):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(
                f"AI Registry file not found : {json_path}"
            )
        with open(path) as f:
            data = json.load(f)
        
        for agent_data in data["agents"]:
            agent = AgentDefinition(**agent_data)
            self.agents[agent.name] = agent

    def get_agent(self, name:str) -> AgentDefinition | None:
        """
        Exact name lookup.
        Returns None if not found - caller must handle this.
        """
        return self.agents.get(name)
    
    def find_by_scenario(self, scenario_key: str) -> AgentDefinition:
        """
        The core routing method.
        
        Takes a full scenario key like 'access_bad_password'
        Extracts prefix 'access'
        Returns the agent whose handles_scenarios contains 'access'
        
        Always returns an agent - falls back to reasoning_agent
        if no match found. System never return None here.
        
        """
        prefix = scenario_key.split("_")[0]
        
        for agent in self.agents.values():
            if not agent.enabled:
                continue
            if prefix in agent.handles_scenarios:
                return agent
            
        logger.warning(
            f"No agent found for prefix '{prefix}"
            f"in scenario '{scenario_key}' -> fallback : reasoning_agent"
        )
        return self.agents.get("reasoning_agent")
    
    def find_by_capability(
        self,
        capability: str
    ) -> list[AgentDefinition]:
        """
        Capability-based discovery.
        Used when orchestrator needs a specific skill
        rather than a scenario match.
        
        Example: find_by_capability("policy_check")
        Returns: [reasoning_agent]
        """
        return [
            agent for agent in self.agents.values() if agent.enabled and capability in agent.capabilities
        ]
    
    def list_agents(self) -> list[AgentDefinition]:
        return [
            agent for agent in self.agents.values() if agent.enabled
        ]
    
    def requires_hitl(self, agent_name: str) -> bool:
        """
        Quick HITL check by agent name.
        Called by orchestrator BEFORE invoking an agent
        to decide whether to interrupt for approval
        
        """
        agent = self.get_agent(agent_name)
        if not agent:
            return True
        
        return agent.requires_hitl

    def summary(self) -> str:
        """
        Human readable summary.
        Printed in CLI, shown in Streamlit dashboard
        """
        
        lines = ["=== AI Resgistry==="]
        for agent in self.list_agents():
                hitl = "⚠️  HITL" if agent.requires_hitl else "✅ Auto"
                lines.append(
                    f"{hitl} | {agent.name} (v{agent.version})\n"
                    f"         Handles    : {', '.join(agent.handles_scenarios)}\n"
                    f"         Capabilities: {', '.join(agent.capabilities)}\n"
                    f"         Tools      : {', '.join(agent.tools_used)}\n"
                )
        return "\n".join(lines)


ai_registry = AIRegistry()
    
        