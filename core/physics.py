import json
import logging
from typing import Dict
from .llm import LLMService

logger = logging.getLogger(__name__)

class GamemasterPhysics:
    """
    Background process that judges interactions and calculates stat impacts.
    """
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def calculate_impact(self, agent_name: str, current_stats: Dict[str, int], user_action: str) -> dict:
        """
        Sends a prompt to the LLM to judge how a user action affects an agent's stats.
        """
        system_prompt = "You are the Game Engine."
        user_prompt = f"""Current Agent: {agent_name}
Current Stats: {current_stats}
Event: The Chairman said '{user_action}'

TASK: How does this event change the stats?

If the Chairman threatens, Loyalty drops.
If the Chairman supports, Confidence rises.
If the event is confusing, Paranoia rises.

Output JSON only. Values for change MUST be integers (e.g. 5, -5). Do NOT include plus signs (+) for positive numbers.

Expected Schema: {{ "confidence_change": int, "paranoia_change": int, "loyalty_change": int, "reasoning": "Brief explanation" }}"""

        try:
            # Using a capable model for logic and JSON formatting
            response_text = self.llm_service.generate_response(
                model_name="gpt-4o", 
                system_prompt=system_prompt,
                user_message=user_prompt
            )
            
            # Extract JSON if LLM includes markers
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Fix common LLM error: including '+' in JSON numbers
            import re
            response_text = re.sub(r':\s*\+(\d+)', r': \1', response_text)
            
            impact = json.loads(response_text)
            return impact
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse physics impact JSON: {e}. Raw response: {response_text}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_change": 0,
                "reasoning": "Error parsing engine response."
            }
        except Exception as e:
            logger.error(f"Error in calculate_impact: {e}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_change": 0,
                "reasoning": f"System error: {str(e)}"
            }
