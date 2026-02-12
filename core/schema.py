from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal


class RelationshipModel(BaseModel):
    """
    Rich relationship with memory and hidden intent.
    Evolves dynamically via the Physics Engine and Dream Phase.
    """
    trust_score: int = Field(default=0, ge=-100, le=100)
    last_interaction_summary: str = ""
    hidden_agenda: Optional[str] = None  # e.g., "Planning to undermine"


class Goal(BaseModel):
    """
    Hierarchical agent goal. Progress is driven by the Physics Engine.
    Goals with progress >= 100 are auto-deactivated.
    """
    description: str
    priority: Literal["strategic", "tactical"] = "tactical"
    active: bool = True
    progress: int = Field(default=0, ge=0, le=100)


class DynamicStats(BaseModel):
    """
    Mutable stats for an agent, constrained between 0 and 100.
    """
    confidence: int = Field(default=50, ge=0, le=100)
    paranoia: int = Field(default=10, ge=0, le=100)
    loyalty_to_chairman: int = Field(default=50, ge=0, le=100)
    stress_level: int = Field(default=0, ge=0, le=100)
    energy: int = Field(default=100, ge=0, le=100)


class AgentSoul(BaseModel):
    """
    The core identity and state of an agent.
    BDI-inspired: Beliefs (relationships), Desires (goals), Intentions (via LLM).
    """
    name: str
    archetype: str
    base_model: str
    core_values: List[str]
    dynamic_stats: DynamicStats
    relationships: Dict[str, RelationshipModel] = Field(default_factory=dict)
    goals: List[Goal] = Field(default_factory=list)

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

    def update_relationship(self, agent_name: str, amount: int, summary: str = ""):
        """
        Safely modify a relationship's trust_score by clamping between -100 and 100.
        Optionally updates the last_interaction_summary.
        Creates the relationship entry if it doesn't exist.
        """
        if agent_name not in self.relationships:
            self.relationships[agent_name] = RelationshipModel()

        rel = self.relationships[agent_name]
        rel.trust_score = max(-100, min(100, rel.trust_score + amount))
        if summary:
            rel.last_interaction_summary = summary

    def update_goal_progress(self, goal_description: str, delta: int):
        """
        Finds a matching active goal by description and updates its progress.
        Clamps progress between 0 and 100.
        """
        for goal in self.goals:
            # FIX BUG-08: Check both directions for substring matching
            gl = goal.description.lower()
            gd = goal_description.lower()
            if goal.active and (gl in gd or gd in gl):
                goal.progress = max(0, min(100, goal.progress + delta))
                return
        # Fuzzy fallback: try partial match
        for goal in self.goals:
            if goal.active and any(
                word in goal_description.lower()
                for word in goal.description.lower().split()
                if len(word) > 3
            ):
                goal.progress = max(0, min(100, goal.progress + delta))
                return

    def check_goal_completion(self) -> List[str]:
        """
        Marks goals with progress >= 100 as inactive.
        Returns list of completed goal descriptions.
        """
        completed = []
        for goal in self.goals:
            if goal.active and goal.progress >= 100:
                goal.active = False
                completed.append(goal.description)
        return completed

    def get_relationship_score(self, agent_name: str) -> int:
        """
        Helper to get the trust_score for a given agent.
        Returns 0 if no relationship exists.
        """
        rel = self.relationships.get(agent_name)
        return rel.trust_score if rel else 0

    def get_serializable_relationships(self) -> Dict[str, dict]:
        """
        Returns relationships as plain dicts for JSON serialization / frontend.
        """
        return {
            name: rel.model_dump()
            for name, rel in self.relationships.items()
        }
