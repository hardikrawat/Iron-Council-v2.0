import os
import json
import logging
from typing import Dict, Any
from core.llm import LLMService

logger = logging.getLogger(__name__)

INTEGRITY_PROMPT_TEMPLATE = """
You are the subconscious ego of {agent_name}.
Your current state is: {state_summary} (Confidence: {conf}, Paranoia: {para}).
The agent drafted this response: "{draft}"
TASK: Does this draft accurately reflect the current state?
- If the agent is Arrogant (Conf > 80), they should NOT apologize.
- If the agent is Paranoid (Para > 60), they should be suspicious.
Output strictly JSON:
{{
  "approved": boolean,
  "critique": "Reason for rejection (if any)",
  "rewrite_suggestion": "How to fix it (if rejected)"
}}
"""


class IntegrityMonitor:
    def __init__(self, llm_service: LLMService, event_bus=None):
        self.llm_service = llm_service
        self.event_bus = event_bus
        # FIX BUG-10: Use dedicated EGO_MODEL env var instead of borrowing General Ares's model
        self.system_model = (
            os.getenv("EGO_MODEL") or os.getenv("GENERAL_ARES_MODEL") or "gpt-3.5-turbo"
        )

    def check_integrity(self, agent_soul: Any, draft_text: str) -> Dict[str, Any]:
        """
        Fills the integrity prompt with agent data and sends it to a fast LLM.
        Returns the parsed JSON decision.
        """
        # Extract data from agent_soul
        agent_name = agent_soul.name
        conf = agent_soul.dynamic_stats.confidence
        para = agent_soul.dynamic_stats.paranoia
        # Assuming we might need a state summary, let's derive it or use archetypes.
        # For now, let's use archetype as a summary.
        state_summary = f"Archetype: {agent_soul.archetype}"

        prompt = INTEGRITY_PROMPT_TEMPLATE.format(
            agent_name=agent_name,
            state_summary=state_summary,
            conf=conf,
            para=para,
            # FIX AUDIT-2.2: Escape draft to prevent prompt injection
            draft=draft_text.replace('"', '\\"').replace("{", "{{").replace("}", "}}"),
        )

        # Using a fast model as requested, or the configured system model
        model_name = self.system_model

        if self.event_bus:
            from core.event_bus import EventType

            self.event_bus.publish_threadsafe(
                EventType.EGO_CHECK,
                {"status": "START", "agent": agent_name, "model": model_name},
            )

        try:
            response_text = self.llm_service.generate_response(
                model_name=model_name,
                system_prompt="You are a JSON integrity generator. Output ONLY valid JSON.",
                user_message=prompt,
            )

            # Clean response text in case of markdown blocks
            if response_text.startswith("```json"):
                response_text = (
                    response_text.replace("```json", "").replace("```", "").strip()
                )
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Failed to check integrity: {e}")
            # FIX MAJ-04: Conservative fallback — reject on error so agents
            # don't bypass the ego filter when the LLM is down.
            return {
                "approved": False,
                "critique": f"Integrity check unavailable: {e}. Holding response.",
                "rewrite_suggestion": "Speak cautiously or remain silent.",
            }
        finally:
            if self.event_bus:
                from core.event_bus import EventType

                self.event_bus.publish_threadsafe(
                    EventType.EGO_CHECK, {"status": "END"}
                )
