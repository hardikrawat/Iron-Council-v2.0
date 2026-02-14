import json
import os
import logging
import tempfile
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
        
        # FIX: Check for environment variable override for the model (e.g., GENERAL_ARES_MODEL)
        # This allows the model to be dynamic based on reconfiguration via setup_env.py
        env_model_key = f"{agent_name.upper().replace(' ', '_')}_MODEL"
        env_model = os.getenv(env_model_key)
        if env_model:
            logger.info(f"[AGENT] Overriding {agent_name} model from soul_state ({self.soul.base_model}) to ENV ({env_model})")
            self.soul.base_model = env_model

        # Initialize services
        self.llm = LLMService(event_bus=event_bus)
        self.integrity = IntegrityMonitor(self.llm, event_bus=event_bus)
        self.memory = SubjectiveMemory(event_bus=event_bus)

    @property
    def id(self) -> str:
        """The canonical snake_case unique identifier for this agent."""
        return self.agent_name

    @property
    def display_name(self) -> str:
        """The human-readable name defined in the soul."""
        return self.soul.name

    def _load_soul(self) -> AgentSoul:
        if not os.path.exists(self.state_path):
            raise FileNotFoundError(f"Soul state file not found for agent '{self.agent_name}' at {self.state_path}")
        
        with open(self.state_path, "r") as f:
            data = f.read()
        
        return AgentSoul.model_validate_json(data)

    def save_state(self):
        """
        Dumps self.soul back to the JSON file to persist changes.
        FIX AUDIT-2.1: Atomic write via tempfile + os.replace to prevent corruption.
        """
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.STATE_SAVE, {"agent": self.agent_name, "op": "SAVE"})

        # Check goal completion before saving
        completed_goals = self.soul.check_goal_completion()
        if completed_goals:
            logger.info(f"[AGENT: {self.agent_name}] Completed goals: {completed_goals}")
            
        state_dir = os.path.dirname(self.state_path)
        fd, temp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(self.soul.model_dump_json(indent=4))
            os.replace(temp_path, self.state_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
        logger.info(f"[AGENT: {self.agent_name}] State saved to disk.")

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
            summary_part = f" (Summary: {rel.last_interaction_summary})" if rel.last_interaction_summary else ""
            if score < -60:
                prompt_parts.append(f"You despise {agent_name}{summary_part}. You would sabotage them.")
            elif score < -20:
                prompt_parts.append(f"You distrust {agent_name}{summary_part}. You suspect their motives.")
            elif score > 60:
                prompt_parts.append(f"You deeply trust {agent_name}{summary_part}. You would ally with them.")
            elif score > 20:
                prompt_parts.append(f"You trust {agent_name}{summary_part} and value their input.")
            elif summary_part:
                prompt_parts.append(f"Regarding {agent_name}:{summary_part}")
            
            # Inject hidden agendas if they exist
            if rel.hidden_agenda:
                prompt_parts.append(f"Regarding {agent_name}, your hidden agenda: {rel.hidden_agenda}")
        
        # Goals — inject active and recently completed goals into the prompt
        active_goals = [g for g in soul.goals if g.active]
        if active_goals:
            goal_strs = [f"{g.description} ({g.priority}, {g.progress}% complete)" for g in active_goals]
            prompt_parts.append(f"Your current active goals: {'; '.join(goal_strs)}. Act in ways that advance them.")
        
        completed_goals = [g for g in soul.goals if not g.active and g.progress >= 100]
        if completed_goals:
            # Only show top 3 mostly recent/relevant completed goals to save tokens
            comp_strs = [f"{g.description}" for g in completed_goals[-3:]]
            prompt_parts.append(f"Recently completed goals: {'; '.join(comp_strs)}. Maintain the momentum of these victories.")
                
        # Formatting Rules — CRITICAL for clean UI
        prompt_parts.append("\nFORMATTING RULES:")
        prompt_parts.append(f"- Output ONLY the spoken dialogue as {soul.name}.")
        prompt_parts.append("- DO NOT prepend your name (e.g., 'General Ares:') to the response.")
        prompt_parts.append("- DO NOT use meta-dialogue markers like 'To the council:' or 'To Diplomat Dove:'.")
        prompt_parts.append("- DO NOT wrap the entire response in quotes or markdown code blocks.")
        prompt_parts.append("- DO NOT use HTML tags (e.g., <p>, <div>, <public_speech>) in your spoken dialogue.")
        prompt_parts.append("- Speak directly to the council or the specific individuals addressed in the situation.")
        
        # FIX: Inner Monologue Instruction (XML Straitjacket)
        prompt_parts.append("\n[OUTPUT FORMAT - STRICT]")
        prompt_parts.append("You are NOT to output raw text. You must format your response precisely as follows:")
        prompt_parts.append("<internal_monologue>")
        prompt_parts.append("Write your private thoughts here. Analyze the situation, check your stats (Paranoia: {stats.paranoia}), and decide your strategy.")
        prompt_parts.append("NO ONE hears this.")
        prompt_parts.append("</internal_monologue>")
        
        prompt_parts.append("<public_speech>")
        prompt_parts.append("Write ONLY what you say out loud to the council.")
        prompt_parts.append("Do not include stage directions like '(shouting)' or actions.")
        prompt_parts.append("</public_speech>")
        
        # FIX: Morning Reflection (Dream Injection)
        try:
            last_dream = self.memory.get_last_dream(self.agent_name)
            if last_dream:
                # Add it as a high-priority state of mind
                prompt_parts.append(f"\nCURRENT STATE OF MIND: You have just woken up. Your last thought was: '{last_dream}'.")
                prompt_parts.append(f"You are feeling: Confidence {stats.confidence}, Paranoia {stats.paranoia}, Loyalty {stats.loyalty_to_chairman}.")
        except Exception as e:
            logger.warning(f"Failed to inject morning reflection: {e}")

        prompt_parts.append("\nExample:")
        prompt_parts.append("<internal_monologue>")
        prompt_parts.append("The Chairman is asking for updates. My paranoia is high (65). I suspect Midas is hiding funds. I should be vague but assertive.")
        prompt_parts.append("</internal_monologue>")
        prompt_parts.append("<public_speech>")
        prompt_parts.append("Chairman, our reserves are secure, though I advise against reckless spending until we audit the latest transaction logs.")
        prompt_parts.append("</public_speech>")
                
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

        # FIX: Soul Anchor Injection
        # Inject the current emotional state at the very bottom of the context
        soul_status = {
            "Identity": f"{self.soul.name} (YOU)",
            "Archetype": self.soul.archetype,
            "Stats": {
                "Confidence": self.soul.dynamic_stats.confidence,
                "Paranoia": self.soul.dynamic_stats.paranoia,
                "Loyalty": self.soul.dynamic_stats.loyalty_to_chairman,
                "Stress": self.soul.dynamic_stats.stress_level,
                "Energy": self.soul.dynamic_stats.energy
            },
            "Active Goals": [g.description for g in self.soul.goals if g.active]
        }
        user_message += f"\n\n[CURRENT SOUL STATUS]\n{json.dumps(soul_status, indent=2)}"
            
        # Step A: Draft response
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {"agent": self.agent_name, "step": "DRAFT"})

        raw_response = self._generate_with_retry(
            system_prompt=system_prompt,
            user_message=user_message
        )
        
        # FIX: Parse XML Straitjacket
        import re
        
        # 1. Default values (in case parsing fails)
        thought_text = ""
        public_draft = raw_response
        
        # 2. Extract Thought (Internal Monologue)
        # Improved regex: more flexible with whitespace and case
        thought_match = re.search(r'<(?:internal_monologue|internal monologue)>(.*?)</(?:internal_monologue|internal monologue)>', raw_response, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thought_text = thought_match.group(1).strip()

        # 3. Extract Speech (Public Output)
        speech_match = re.search(r'<public_speech>(.*?)</public_speech>', raw_response, re.DOTALL | re.IGNORECASE)
        if speech_match:
            public_draft = speech_match.group(1).strip()
        else:
            # Fallback A: If agent forgot speech tags but used monologue tags
            # Assume everything NOT in monologue tags is speech
            if thought_match:
                cleaner = re.sub(r'<(?:internal_monologue|internal monologue)>.*?</(?:internal_monologue|internal monologue)>', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
                public_draft = cleaner.strip()
            
            # Fallback B: If agent used OLD format (THOUGHT) despite instructions (Legacy Drift)
            old_thought_match = re.search(r"\(THOUGHT\)\s*(.*?)\s*\(RESPONSE\)", raw_response, re.DOTALL | re.IGNORECASE)
            if old_thought_match:
                 thought_text = old_thought_match.group(1).strip()
                 cleaner = re.sub(r"\(THOUGHT\)\s*.*?\s*\(RESPONSE\)", "", raw_response, flags=re.DOTALL | re.IGNORECASE)
                 public_draft = cleaner.strip()

        # Step B: Integrity check (Only on public draft)
        check = self.integrity.check_integrity(self.soul, public_draft)
        
        # Step C: The Gate
        if check.get("approved"):
            logger.info(f"[AGENT: {self.agent_name}] Ego APPROVED draft. Speaking directly.")
            return {
                "public_text": clean_agent_response(public_draft, self.agent_name),
                "hidden_text": thought_text if thought_text else "" 
            }
        
        # Step D: Rewrite
        critique = check.get("critique", "No critique provided.")
        # If rejected, we show the thought AND the rejected draft in hidden text
        # FIX: Use human-friendly labels instead of XML-like tags to prevent leakage
        hidden_thought = f"[INTERNAL MONOLOGUE]: {thought_text}\n[REJECTED DRAFT]: {public_draft}\n[CRITIQUE]: {critique}"
        
        logger.info(f"[AGENT: {self.agent_name}] Ego REJECTED draft. Critique: {critique}")
        
        rewrite_prompt = (
            f"{system_prompt}\n\n"
            f"Your previous draft was rejected by your Ego because: {critique}. "
            "Rewrite ONLY the <public_speech> to be more true to your current state. "
            "You MUST wrap your rewritten speech in <public_speech></public_speech> tags. "
            "Do NOT include any preamble, thoughts, or analysis outside the tags. "
            "Output ONLY: <public_speech>Your rewritten speech here.</public_speech>"
        )
        
        # Step E: Generate Rewritten Response
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {"agent": self.agent_name, "step": "REWRITE"})

        final_response = self._generate_with_retry(
            system_prompt=rewrite_prompt,
            user_message=user_message
        )
        
        # Step F: Final Clean — Apply same XML extraction as Step A (NOT naive .replace())
        rewrite_speech_match = re.search(r'<public_speech>(.*?)</public_speech>', final_response, re.DOTALL | re.IGNORECASE)
        if rewrite_speech_match:
            final_clean = clean_agent_response(rewrite_speech_match.group(1).strip(), self.agent_name)
        else:
            # Fallback: Strip any tags and preamble, take what remains
            stripped = re.sub(r'<internal_monologue>.*?</internal_monologue>', '', final_response, flags=re.DOTALL | re.IGNORECASE)
            stripped = re.sub(r'</?(?:public_speech|internal_monologue)>', '', stripped, flags=re.IGNORECASE)
            final_clean = clean_agent_response(stripped.strip(), self.agent_name)
        
        return {
            "public_text": final_clean,
            "hidden_text": hidden_thought
        }
