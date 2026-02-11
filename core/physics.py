import os
import json
import logging
import re
from typing import Dict, List, Optional, TYPE_CHECKING, Union
from .llm import LLMService

if TYPE_CHECKING:
    from core.schema import AgentSoul

logger = logging.getLogger(__name__)


class GamemasterPhysics:
    """
    Background process that judges interactions and calculates stat impacts.

    DOMAIN SEPARATION:
    - calculate_impact()  → User ↔ Agent (Used in both modes)
    - reconcile_turn()    → Agent ↔ Agent (Legacy/Terminal Mode ONLY)
    - calculate_relationship_update() → Agent ↔ Agent (Event-Driven/Web Mode ONLY)
    """
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        # Default system model — can be overridden by env
        self.system_model = os.getenv("GENERAL_ARES_MODEL") or "gpt-4o"

    def calculate_impact(
        self,
        user_input: str,
        agent_soul: "AgentSoul"
    ) -> dict:
        """
        User ↔ Agent ONLY. Calculates how the Chairman's action affects
        this agent's personal stats and goal progress.
        
        Args:
            user_input: The Chairman's statement/action.
            agent_soul: The target agent's soul object.
        """
        agent_name = agent_soul.name
        current_stats = agent_soul.dynamic_stats.model_dump()
        agent_goals = [g.description for g in agent_soul.goals if g.active]

        # Build goals context
        goals_context = ""
        if agent_goals:
            goals_context = f"\nAgent's Active Goals: {', '.join(agent_goals)}"

        system_prompt = "You are the Game Engine. You analyze how the Chairman's words affect an agent's psyche and goals."
        user_prompt = f"""Current Agent: {agent_name}
Current Stats: {current_stats}
Event: The Chairman said '{user_input}'{goals_context}

TASK: How does the Chairman's statement change {agent_name}'s personal stats and goal progress?

RULES:
- ONLY consider the Chairman's direct words. Do NOT consider other agents.
- If the Chairman threatens, Loyalty drops. If the Chairman supports, Confidence rises.
- If the event is confusing or suspicious, Paranoia rises.
- If the event is urgent or alarming, Stress rises.
- If the Chairman's action advanced one of the agent's goals, increase that goal's progress.
- If the Chairman's action hindered a goal, decrease that goal's progress.

Output JSON only. Values MUST be integers (e.g. 5, -5). Do NOT include plus signs (+).

Expected Schema:
{{
    "confidence_change": int,
    "paranoia_change": int,
    "loyalty_change": int,
    "stress_change": int,
    "reasoning": "Brief explanation",
    "goal_updates": {{ "Goal description keyword": int, ... }}
}}"""

        try:
            response_text = self.llm_service.generate_response(
                model_name=self.system_model,
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
            
            # Standardize keys to match Schema
            impact["loyalty_to_chairman_change"] = impact.pop("loyalty_change", 0)
            impact["stress_level_change"] = impact.pop("stress_change", 0)

            # Safe cast to int
            for k in ["confidence_change", "paranoia_change", "loyalty_to_chairman_change", "stress_level_change", "energy_change"]:
                try:
                    impact[k] = int(impact.get(k, 0))
                except (ValueError, TypeError):
                    impact[k] = 0

            # Ensure goal_updates exists
            impact.setdefault("goal_updates", {})
            # Legacy compat — no longer populated here, but keep key for callers
            impact.setdefault("relationship_changes", {})

            logger.info(f"[PHYSICS] Calculated impact for {agent_name}: Loyalty {impact.get('loyalty_to_chairman_change')}, Stress {impact.get('stress_level_change')}")
            return impact

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse physics impact JSON: {e}. Raw response: {response_text}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_to_chairman_change": 0,
                "stress_level_change": 0,
                "reasoning": "Error parsing engine response.",
                "relationship_changes": {},
                "goal_updates": {}
            }
        except Exception as e:
            logger.error(f"Error in calculate_impact: {e}")
            return {
                "confidence_change": 0,
                "paranoia_change": 0,
                "loyalty_to_chairman_change": 0,
                "stress_level_change": 0,
                "reasoning": f"System error: {str(e)}",
                "relationship_changes": {},
                "goal_updates": {}
            }

    def reconcile_turn(
        self,
        # Granular Mode (Architecture Standard)
        speaker_soul: Optional["AgentSoul"] = None,
        listener_soul: Optional["AgentSoul"] = None,
        statement: str = None,
        transcript: List = None,
        # Batch Mode (Legacy)
        agent_responses: Optional[List[Dict[str, str]]] = None,
        agent_core_values: Optional[Dict[str, List[str]]] = None
    ) -> Dict:
        """
        Evaluates interaction logic. Two modes:
        1. Granular (Architecture): Updates listener's trust based on speaker.
           Returns {listener: {speaker: delta}}.
        2. Batch (Legacy): Updates matrix for all agents.
        """
        # Mode 1: Granular
        if speaker_soul and listener_soul and statement:
            delta = self.calculate_relationship_update(speaker_soul.name, statement, listener_soul)
            # Return dict format expected by tests/architecture
            # Note: Tests expect { "trust_delta": int, ... } or similar?
            # test_alliance_betrayal.py expects result[trust_key] to be the delta
            # The tests inspect the RETURN value look for "trust...".
            # The Architecture doc says returns Dict[str, Dict[str, int]].
            
            logger.info(f"[PHYSICS] Granular update: {listener_soul.name} -> {speaker_soul.name} | Delta: {delta}")
            return {listener_soul.name: {speaker_soul.name: delta}}

        # Mode 2: Batch
        if not agent_responses or len(agent_responses) < 2:
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
                model_name=self.system_model,
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


    def calculate_relationship_update(
        self,
        speaker_name: str,
        content: str,
        listener_soul: Union["AgentSoul", object] 
    ) -> int:
        """
        Calculates the change in trust for a listener agent based on what a speaker said.
        Updates the listener's relationship with the speaker directly.
        Returns the delta for logging/debugging.
        """
        # Handle IronAgent wrapper if passed (Legacy compatibility)
        if hasattr(listener_soul, "soul"):
            listener_soul = listener_soul.soul
            
        # Self-talk check
        if speaker_name == listener_soul.name:
            return 0

        # Current relationship context
        current_rel = listener_soul.relationships.get(speaker_name)
        current_trust = current_rel.trust_score if current_rel else 0

        system_prompt = (
            f"You are the Relationship Engine. You determine how {listener_soul.name}'s "
            f"opinion of {speaker_name} changes based on their recent statement."
        )
        
        user_prompt = f"""
Listener: {listener_soul.name}
Listener's Core Values: {', '.join(listener_soul.core_values)}
Current Trust in Speaker: {current_trust}

Speaker: {speaker_name}
Statement: "{content}"

TASK:
Determine the Trust Delta (change in trust score).
- Range: -15 to +15.
- If the statement aligns with Listener's values -> Positive.
- If the statement contradicts Listener's values -> Negative.
- If the statement is neutral/irrelevant -> 0.
- If the statement attacks the Listener -> Highly Negative.

Output ONLY an integer.
"""

        try:
            response_text = self.llm_service.generate_response(
                model_name=self.system_model,
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            # Clean up response
            response_text = response_text.strip()
            # Remove any markdown or extra text
            match = re.search(r'-?\d+', response_text)
            if match:
                 delta = int(match.group())
            else:
                 logger.warning(f"Could not parse delta from LLM: {response_text}")
                 delta = 0

            # Clamp delta
            delta = max(-15, min(15, delta))

            # Update Relationship
            if delta != 0:
                listener_soul.update_relationship(speaker_name, delta)
                logger.info(f"[RELATIONSHIP] {listener_soul.name} -> {speaker_name}: Delta {delta} (New Total: {listener_soul.relationships[speaker_name].trust_score})")
            
            return delta

        except Exception as e:
            logger.error(f"Error in calculate_relationship_update: {e}")
            return 0
