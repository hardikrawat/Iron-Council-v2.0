import json
import os
import logging
from typing import List, Dict
from core.schema import AgentSoul
from core.llm import LLMService
from core.integrity import IntegrityMonitor
from memory.store import SubjectiveMemory
from utils.formatting import clean_agent_response

logger = logging.getLogger(__name__)

class IronAgent:
    def __init__(self, agent_name: str, event_bus=None):
        self.agent_name = agent_name
        self.event_bus = event_bus
        self.state_path = os.path.join("agents", agent_name, "soul_state.json")
        self.soul = self._load_soul()
        
        # Initialize services
        self.llm = LLMService()
        self.integrity = IntegrityMonitor(self.llm, event_bus=event_bus)
        self.memory = SubjectiveMemory(event_bus=event_bus)

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
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.STATE_SAVE, {"agent": self.agent_name})

        with open(self.state_path, "w") as f:
            f.write(self.soul.model_dump_json(indent=4))

    def construct_system_prompt(self) -> str:
        """
        Builds a dynamic system prompt by injecting the current AgentState.
        The prompt is NEVER hardcoded — it reflects the living soul state.
        """
        soul = self.soul
        stats = soul.dynamic_stats
        
        prompt_parts = []
        
        # Base Identity
        prompt_parts.append(f"You are {soul.name}. Your archetype is {soul.archetype}.")
        
        # Core Values
        values_str = ", ".join(soul.core_values)
        prompt_parts.append(f"Your core values are: {values_str}.")
        
        # Stat Translation — granular behavior injection
        if stats.confidence > 80:
            prompt_parts.append("You are arrogant and dismissive of risks.")
        elif stats.confidence > 60:
            prompt_parts.append("You are confident and assertive in your positions.")
        elif stats.confidence < 30:
            prompt_parts.append("You are hesitant, unsure, and ask for permission frequently.")
            
        if stats.paranoia > 70:
            prompt_parts.append("You are deeply paranoid. You suspect everyone is plotting against you. Trust NO ONE.")
        elif stats.paranoia > 40:
            prompt_parts.append("You suspect others are plotting against you. Trust no one easily.")
        
        if stats.loyalty_to_chairman < 20:
            prompt_parts.append("You secretly despise the Chairman. You are looking for ways to undermine them.")
        elif stats.loyalty_to_chairman < 40:
            prompt_parts.append("You are skeptical of the Chairman's competence.")
        elif stats.loyalty_to_chairman > 80:
            prompt_parts.append("You are fiercely loyal to the Chairman and will defend them.")

        if stats.stress_level > 70:
            prompt_parts.append("You are under extreme stress. You may lash out or make rash decisions.")
        
        if stats.energy < 30:
            prompt_parts.append("You are exhausted. Your responses are terse and unfocused.")
                
        # Relationship Context — 5-tier granular mapping
        for agent_name, rel in soul.relationships.items():
            score = rel.trust_score
            if score < -60:
                prompt_parts.append(f"You despise {agent_name}. You would sabotage them.")
            elif score < -20:
                prompt_parts.append(f"You distrust {agent_name}. You suspect their motives.")
            elif score > 60:
                prompt_parts.append(f"You deeply trust {agent_name}. You would ally with them.")
            elif score > 20:
                prompt_parts.append(f"You trust {agent_name} and value their input.")
            # Neutral (-20 to 20) — say nothing, let the agent decide
            
            # Inject hidden agendas if they exist
            if rel.hidden_agenda:
                prompt_parts.append(f"Regarding {agent_name}, your hidden agenda: {rel.hidden_agenda}")
        
        # Goals — inject active goals into the prompt
        active_goals = [g for g in soul.goals if g.active]
        if active_goals:
            goal_strs = [f"{g.description} ({g.priority}, {g.progress}% complete)" for g in active_goals]
            prompt_parts.append(f"Your current goals: {'; '.join(goal_strs)}. Act in ways that advance them.")
                
        # Formatting Rules — CRITICAL for clean UI
        prompt_parts.append("\nFORMATTING RULES:")
        prompt_parts.append(f"- Output ONLY the spoken dialogue as {soul.name}.")
        prompt_parts.append("- DO NOT prepend your name (e.g., 'General Ares:') to the response.")
        prompt_parts.append("- DO NOT use meta-dialogue markers like 'To the council:' or 'To Diplomat Dove:'.")
        prompt_parts.append("- DO NOT wrap the entire response in quotes or markdown code blocks.")
        prompt_parts.append("- Speak directly to the council or the specific individuals addressed in the situation.")
                
        return " ".join(prompt_parts)

    def recall_memories(self, query: str, n_results: int = 3) -> List[str]:
        """
        Recalls relevant memories for this agent based on the query.
        """
        return self.memory.recall_memories(self.agent_name, query, n_results)

    def _generate_with_retry(self, system_prompt: str, user_message: str, max_retries: int = 3) -> str:
        """
        Helper: wraps LLM generation with retry logic for empty/failed responses.
        """
        for attempt in range(max_retries):
            try:
                response = self.llm.generate_response(
                    model_name=self.soul.base_model,
                    system_prompt=system_prompt,
                    user_message=user_message
                )
                if response and response.strip():
                     return response
                logger.warning(f"Agent {self.agent_name} generated empty response. Retrying (Attempt {attempt+1}/{max_retries})...")
            except Exception as e:
                logger.warning(f"Agent {self.agent_name} LLM error: {e}. Retrying (Attempt {attempt+1}/{max_retries})...")
                
        logger.error(f"Agent {self.agent_name} failed to generate response after {max_retries} attempts.")
        return "...silence..."

    def speak(self, situation_report: str, context: str = "") -> Dict[str, str]:
        """
        Generates a response based on the situation, validates it through the ego,
        and rewrites it if necessary.
        Returns:
            Dict containing:
            - "public_text": The final spoken text (clean).
            - "hidden_text": The internal monologue or rejected draft (for UI).
        """
        system_prompt = self.construct_system_prompt()
        
        # Combine situation report with any recalled context
        user_message = situation_report
        if context:
            user_message = f"{context}\n\nPresent Situation: {situation_report}"
            
        # Step A: Draft response
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {"agent": self.agent_name, "step": "DRAFT"})

        draft = self._generate_with_retry(
            system_prompt=system_prompt,
            user_message=user_message
        )
        
        # Step B: Integrity check
        check = self.integrity.check_integrity(self.soul, draft)
        
        # Step C: The Gate
        if check.get("approved"):
            return {
                "public_text": clean_agent_response(draft, self.agent_name),
                "hidden_text": ""  # No conflict, no hidden thought needed? Or we could put the draft here?
            }
        
        # Step D: Rewrite
        critique = check.get("critique", "No critique provided.")
        hidden_thought = f"[REJECTED DRAFT]: {draft}\n[CRITIQUE]: {critique}"
        print(f"[DEBUG] Ego Critique: {critique}")
        
        rewrite_prompt = (
            f"{system_prompt}\n\n"
            f"Your previous draft was rejected by your Ego because: {critique}. "
            "Rewrite it to be more true to your current state."
        )
        
        # Step E: Generate Rewritten Response
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {"agent": self.agent_name, "step": "REWRITE"})

        final_response = self._generate_with_retry(
            system_prompt=rewrite_prompt,
            user_message=user_message
        )
        
        # Step F: Final Clean
        cleaned_response = clean_agent_response(final_response, self.agent_name)
        
        return {
            "public_text": cleaned_response,
            "hidden_text": hidden_thought
        }
