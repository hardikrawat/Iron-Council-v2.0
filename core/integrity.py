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
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

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
            draft=draft_text
        )
        
        # Using a fast model as requested
        model_name = "gpt-3.5-turbo"
        
        try:
            response_text = self.llm_service.generate_response(
                model_name=model_name,
                system_prompt="You are a JSON integrity generator. Output ONLY valid JSON.",
                user_message=prompt
            )
            
            # Clean response text in case of markdown blocks
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
            
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Failed to check integrity: {e}")
            # Fallback response in case of failure
            return {
                "approved": True,
                "critique": f"Integrity check failed: {e}",
                "rewrite_suggestion": None
            }
