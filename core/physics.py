import json
import logging
import re
from typing import Dict, List, Optional
from .llm import LLMService

logger = logging.getLogger(__name__)


class GamemasterPhysics:
    """
    Background process that judges interactions and calculates stat impacts.

    DOMAIN SEPARATION:
    - calculate_impact()  → User ↔ Agent ONLY (stats + goals)
    - reconcile_turn()    → Agent ↔ Agent ONLY (relationship trust deltas)
    """
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def calculate_impact(
        self,
        agent_name: str,
        current_stats: Dict[str, int],
        user_action: str,
        agent_goals: Optional[List[str]] = None
    ) -> dict:
        """
        User ↔ Agent ONLY. Calculates how the Chairman's action affects
        this agent's personal stats and goal progress.
        Does NOT process agent-to-agent dynamics (that's reconcile_turn's job).
        """
        if agent_goals is None:
            agent_goals = []

        # Build goals context
        goals_context = ""
        if agent_goals:
            goals_context = f"\nAgent's Active Goals: {', '.join(agent_goals)}"

        system_prompt = "You are the Game Engine. You analyze how the Chairman's words affect an agent's psyche and goals."
        user_prompt = f"""Current Agent: {agent_name}
Current Stats: {current_stats}
Event: The Chairman said '{user_action}'{goals_context}

TASK: How does the Chairman's statement change {agent_name}'s personal stats and goal progress?

RULES:
- ONLY consider the Chairman's direct words. Do NOT consider other agents.
- If the Chairman threatens, Loyalty drops. If the Chairman supports, Confidence rises.
- If the event is confusing or suspicious, Paranoia rises.
- If the Chairman's action advanced one of the agent's goals, increase that goal's progress.
- If the Chairman's action hindered a goal, decrease that goal's progress.

Output JSON only. Values MUST be integers (e.g. 5, -5). Do NOT include plus signs (+).

Expected Schema:
{{
    "confidence_change": int,
    "paranoia_change": int,
    "loyalty_change": int,
    "reasoning": "Brief explanation",
    "goal_updates": {{ "Goal description keyword": int, ... }}
}}"""

        try:
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
            response_text = re.sub(r':\s*\+(\d+)', r': \1', response_text)

            impact = json.loads(response_text)

            # Ensure goal_updates exists
            impact.setdefault("goal_updates", {})
            # Legacy compat — no longer populated here, but keep key for callers
            impact.setdefault("relationship_changes", {})

            return impact

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse physics impact JSON: {e}. Raw response: {response_text}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_change": 0,
                "reasoning": "Error parsing engine response.",
                "relationship_changes": {},
                "goal_updates": {}
            }
        except Exception as e:
            logger.error(f"Error in calculate_impact: {e}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_change": 0,
                "reasoning": f"System error: {str(e)}",
                "relationship_changes": {},
                "goal_updates": {}
            }

    def reconcile_turn(
        self,
        agent_responses: List[Dict[str, str]],
        agent_core_values: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, int]]:
        """
        Agent ↔ Agent ONLY. Called ONCE after all agents have spoken.
        Evaluates semantic alignment between every pair of agents and returns
        a trust delta matrix.

        Phase 2.6: Also extracts explicit votes (A/B) and applies deterministic
        penalties for opposing votes, overriding sentiment analysis.

        Args:
            agent_responses: List of {"name": "Agent Name", "public_text": "What they said"}
            agent_core_values: {"Agent Name": ["Value1", "Value2", ...]}

        Returns:
            {"Agent Name": {"Other Agent": trust_delta, ..., "vote": "A"|"B"|"None"}, ...}
        """
        if len(agent_responses) < 2:
            return {}

        # Build the transcript
        transcript_lines = []
        for resp in agent_responses:
            name = resp["name"]
            values = agent_core_values.get(name, [])
            transcript_lines.append(
                f"- {name} (Values: {', '.join(values)}): \"{resp['public_text'][:300]}\""
            )
        transcript = "\n".join(transcript_lines)
        agent_names = [r["name"] for r in agent_responses]

        system_prompt = "You are the Relationship Engine. You ONLY analyze Agent-to-Agent dynamics."
        user_prompt = f"""The following agents just spoke in the council:

{transcript}

TASK: For EACH agent, determine:
1. How EVERY other agent's words affected their trust.
2. What explicit VOTE (if any) each agent cast.

SEMANTIC ALIGNMENT RULES:
- If Agent B defends or endorses Agent A's core values, Agent A's trust toward B RISES (+10 to +25).
- If Agent B attacks, contradicts, or undermines Agent A's core values, Agent A's trust toward B DROPS (-10 to -25).
- If Agent B explicitly names Agent A positively ("has the expertise", "I support"), trust RISES strongly.
- If Agent B explicitly names Agent A negatively ("incompetent", "naive", "failed"), trust DROPS strongly.
- SARCASM CHECK: If words say "I agree" but the tone is clearly mocking or dismissive, score NEGATIVE.
- If Agent B's statement is neutral toward Agent A, output 0 for that pair.

VOTE EXTRACTION RULES:
- For each agent, extract their FINAL decision/vote if one exists.
- Look for phrases like "I vote...", "I choose...", "I support Option...", "My decision is..."
- IGNORE hypothetical discussion. If an agent says "Option A is interesting but I choose B", the vote is "B", NOT "A".
- If no clear vote was cast, set vote to "None".

Output ONLY a JSON object. Keys are agent names, values are objects mapping other agents to trust deltas, PLUS a "vote" field.
Values MUST be integers. Do NOT include plus signs (+).

Expected Schema (for {len(agent_names)} agents):
{{
{chr(10).join(f'    "{name}": {{ "vote": "A"|"B"|"None", {", ".join(f"{chr(34)}{other}{chr(34)}: int" for other in agent_names if other != name)} }}' for name in agent_names)}
}}"""

        try:
            response_text = self.llm_service.generate_response(
                model_name="gpt-4o",
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            response_text = re.sub(r':\s*\+(\d+)', r': \1', response_text)

            matrix = json.loads(response_text)

            # --- Phase 2.6: Extract votes and detect hard conflicts ---
            votes = {}
            for agent_name in list(matrix.keys()):
                if isinstance(matrix[agent_name], dict):
                    vote = str(matrix[agent_name].pop("vote", "None")).upper()
                    if vote in ["A", "B"]:
                        votes[agent_name] = vote
                    else:
                        votes[agent_name] = "None"
                else:
                    votes[agent_name] = "None"

            logger.info(f"[RECONCILIATION] Extracted votes: {votes}")

            # Validate: ensure all values are ints, filter out self-references
            clean_matrix: Dict[str, Dict[str, int]] = {}
            for agent_name, deltas in matrix.items():
                if not isinstance(deltas, dict):
                    continue
                clean_matrix[agent_name] = {}
                for target, delta in deltas.items():
                    if target != agent_name and isinstance(delta, (int, float)):
                        clean_matrix[agent_name][target] = int(delta)

            # --- Phase 2.6: Apply deterministic penalties for opposing votes ---
            for agent_a in list(clean_matrix.keys()):
                vote_a = votes.get(agent_a, "None")
                if vote_a in ["A", "B"]:
                    for agent_b in list(clean_matrix.keys()):
                        if agent_a == agent_b:
                            continue
                        vote_b = votes.get(agent_b, "None")
                        if vote_b in ["A", "B"] and vote_a != vote_b:
                            # Hard conflict: override any positive sentiment
                            old_val = clean_matrix[agent_a].get(agent_b, 0)
                            new_val = min(old_val, -15)
                            clean_matrix[agent_a][agent_b] = new_val
                            logger.warning(
                                f"[HARD_VOTE_CONFLICT] {agent_a} (voted {vote_a}) vs "
                                f"{agent_b} (voted {vote_b}): trust penalty {old_val} -> {new_val}"
                            )

            # Attach votes to matrix for downstream consumers
            for agent_name in clean_matrix:
                clean_matrix[agent_name]["vote"] = votes.get(agent_name, "None")

            logger.info(f"Reconciliation matrix: {clean_matrix}")
            return clean_matrix

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse reconciliation JSON: {e}. Raw: {response_text}")
            return {}
        except Exception as e:
            logger.error(f"Error in reconcile_turn: {e}")
            return {}

