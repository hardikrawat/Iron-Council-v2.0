from pydantic import BaseModel, Field, conint
from typing import List, Dict

class DynamicStats(BaseModel):
    """
    Mutable stats for an agent, constrained between 0 and 100.
    """
    confidence: int = Field(default=50, ge=0, le=100)
    paranoia: int = Field(default=10, ge=0, le=100)
    loyalty_to_chairman: int = Field(default=50, ge=0, le=100)
    stress_level: int = Field(default=0, ge=0, le=100)

class AgentSoul(BaseModel):
    """
    The core identity and state of an agent.
    """
    name: str
    archetype: str
    base_model: str
    core_values: List[str]
    dynamic_stats: DynamicStats
    relationships: Dict[str, int] = Field(default_factory=dict)

    def update_stat(self, stat_name: str, amount: int):
        """
        Safely modify a stat by clamping it between 0 and 100.
        """
        if hasattr(self.dynamic_stats, stat_name):
            current_val = getattr(self.dynamic_stats, stat_name)
            new_val = max(0, min(100, current_val + amount))
            setattr(self.dynamic_stats, stat_name, new_val)
        else:
            raise AttributeError(f"Stat '{stat_name}' does not exist in DynamicStats.")

    def update_relationship(self, agent_name: str, amount: int):
        """
        Safely modify a relationship score by clamping it between -100 and 100.
        """
        current_val = self.relationships.get(agent_name, 0)
        new_val = max(-100, min(100, current_val + amount))
        self.relationships[agent_name] = new_val
