import json
import os
import logging
from typing import List
from core.schema import AgentSoul
from core.llm import LLMService
from core.integrity import IntegrityMonitor
from memory.store import SubjectiveMemory

logger = logging.getLogger(__name__)

class IronAgent:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.state_path = os.path.join("agents", agent_name, "soul_state.json")
        self.soul = self._load_soul()
        
        # Initialize services
        self.llm = LLMService()
        self.integrity = IntegrityMonitor(self.llm)
        self.memory = SubjectiveMemory()

    def _load_soul(self) -> AgentSoul:
        if not os.path.exists(self.state_path):
            raise FileNotFoundError(f"Soul state file not found for agent '{self.agent_name}' at {self.state_path}")
        
        with open(self.state_path, "r") as f:
            data = f.read()
        
        return AgentSoul.model_validate_json(data)

    def save_state(self):
        """
        Dumps self.soul back to the JSON file to persist changes.
        """
        with open(self.state_path, "w") as f:
            f.write(self.soul.model_dump_json(indent=4))

    def construct_system_prompt(self) -> str:
        """
        Builds a string that tells the LLM how to act based on its current stats.
        """
        soul = self.soul
        stats = soul.dynamic_stats
        
        prompt_parts = []
        
        # Base Identity
        prompt_parts.append(f"You are {soul.name}. Your archetype is {soul.archetype}.")
        
        # Core Values
        values_str = ", ".join(soul.core_values)
        prompt_parts.append(f"Your core values are: {values_str}.")
        
        # Stat Translation
        if stats.confidence > 80:
            prompt_parts.append("You are arrogant and dismissive of risks.")
        elif stats.confidence < 30:
            prompt_parts.append("You are hesitant, unsure, and ask for permission frequently.")
            
        if stats.paranoia > 60:
            prompt_parts.append("You suspect others are plotting against you. Trust no one.")
            
        if stats.loyalty_to_chairman < 20:
            prompt_parts.append("You secretly despise the Chairman. You are looking for ways to undermine them.")
            
        # Relationship Context
        for agent_name, score in soul.relationships.items():
            if score < -20:
                prompt_parts.append(f"You hate {agent_name}.")
            elif score > 20:
                prompt_parts.append(f"You trust {agent_name}.")
                
        return " ".join(prompt_parts)

    def recall_memories(self, query: str, n_results: int = 3) -> List[str]:
        """
        Recalls relevant memories for this agent based on the query.
        """
        return self.memory.recall_memories(self.agent_name, query, n_results)

    def speak(self, situation_report: str, context: str = "") -> str:
        """
        Generates a response based on the situation, validates it through the ego,
        and rewrites it if necessary.
        """
        system_prompt = self.construct_system_prompt()
        
        # Combine situation report with any recalled context
        user_message = situation_report
        if context:
            user_message = f"{context}\n\nPresent Situation: {situation_report}"
            
        # Step A: Draft response
        draft = self.llm.generate_response(
            model_name=self.soul.base_model,
            system_prompt=system_prompt,
            user_message=user_message
        )
        
        # Step B: Integrity check
        check = self.integrity.check_integrity(self.soul, draft)
        
        # Step C: The Gate
        if check.get("approved"):
            return draft
        
        # Step D: Rewrite
        critique = check.get("critique", "No critique provided.")
        print(f"[DEBUG] Ego Critique: {critique}")
        
        rewrite_prompt = (
            f"{system_prompt}\n\n"
            f"Your previous draft was rejected by your Ego because: {critique}. "
            "Rewrite it to be more true to your current state."
        )
        
        final_response = self.llm.generate_response(
            model_name=self.soul.base_model,
            system_prompt=rewrite_prompt,
            user_message=user_message
        )
        
        return final_response
