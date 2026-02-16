import asyncio
import json
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


async def dream_phase(
    agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None
) -> str:
    """
    Synthesizes the chat log into a subjective diary entry, effectively 'dreaming'.
    Uses a multi-stage validation and self-correction loop to ensure valid JSON output.
    """
    system_prompt, original_user_message = _prepare_dream_prompts(
        agent, raw_chat_log, trust_deltas
    )
    user_message = original_user_message

    if agent.event_bus:
        from core.event_bus import EventType

        agent.event_bus.publish_threadsafe(
            EventType.LLM_ACTIVITY, {"agent": agent.id, "step": "DREAM_SYNTHESIS"}
        )

    logger.info(f"[DREAM] Synthesizing dream for {agent.display_name}...")

    max_retries = 3
    last_error = ""
    last_response = ""

    for attempt in range(max_retries):
        # Apply feedback if this is a retry
        current_user_message = user_message
        if attempt > 0:
            current_user_message = (
                f"{original_user_message}\n\n"
                f"### FEEDBACK ON PREVIOUS ATTEMPT ###\n"
                f"Your previous output was NOT valid JSON.\n"
                f"Error: {last_error}\n"
                f"Please fix the JSON structure, ensuring all quotes are closed, commas are correct, "
                f"and numbers do not have illegal symbols like '+'.\n"
                f"Output ONLY the fixed JSON object."
            )

        try:
            response_text = await asyncio.to_thread(
                agent.llm.generate_response,
                model_name=agent.soul.base_model,
                system_prompt=system_prompt,
                user_message=current_user_message,
            )
            last_response = response_text
        except Exception as e:
            logger.error(f"[DREAM] LLM generation failed (Attempt {attempt+1}): {e}")
            if attempt == max_retries - 1:
                return "I sleep without dreams."
            continue

        # 2. Parse & Repair
        success, dream_data, error_msg = _intelligent_json_recovery(response_text)

        if success:
            logger.info(
                f"[DREAM] Successfully obtained dream data for {agent.display_name} on attempt {attempt+1}."
            )
            return _apply_dream_consequences(agent, dream_data)
        else:
            last_error = error_msg
            logger.warning(
                f"[DREAM] JSON validation failed for {agent.display_name} (Attempt {attempt+1}/3): {error_msg}"
            )

    # FINAL FAILOVER: Lossy extraction of narrative via regex
    logger.error(
        f"[DREAM] Failed to get valid JSON for {agent.display_name} after {max_retries} attempts. Using lossy recovery."
    )
    narrative_match = re.search(
        r'"dream_narrative"\s*:\s*"(.*?)"', last_response, re.DOTALL
    )
    if narrative_match:
        recovered_narrative = narrative_match.group(1).strip()
        return _apply_dream_consequences(
            agent, {"dream_narrative": recovered_narrative}
        )

    # Absolute last resort
    return "I contemplated the void, but the visions were fragmented and unreadable."


def _intelligent_json_recovery(text: str) -> tuple[bool, dict, str]:
    """
    Applies heuristics to find and fix JSON within a potentially messy string.
    Returns (success, data, error_message).
    """
    try:
        # Stage 1: Basic Extraction (Braces/Markdown)
        cleaned = text.strip()
        # Remove inline comments
        cleaned = re.sub(r"//.*", "", cleaned)

        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1].strip()

        # Stage 2: Heuristic Repairs
        # 1. Strip '+' signs before numbers: {"val": +10} -> {"val": 10}
        cleaned = re.sub(r":\s*\+(\d+)", r": \1", cleaned)

        # 2. Fix unescaped newlines in values (common failure for local LLMs)
        # This is tricky; we look for newlines that aren't followed by a key separator or brace
        # Simple version: replace newlines inside quotes
        def _fix_newlines(match):
            return match.group(0).replace("\n", "\\n")

        cleaned = re.sub(r'"([^"]*)"', _fix_newlines, cleaned, flags=re.DOTALL)

        # Stage 3: Recursive Brace Matching for Extraction
        # Sometimes LLMs wrap JSON in text: "Here is your JSON: { ... } Hope this helps"
        if not (cleaned.startswith("{") and cleaned.endswith("}")):
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}")
            if json_start != -1 and json_end != -1:
                cleaned = cleaned[json_start : json_end + 1]

        # Stage 4: Parse
        data = json.loads(cleaned)
        return True, data, ""
    except json.JSONDecodeError as e:
        return False, {}, str(e)
    except Exception as e:
        return False, {}, f"Unexpected recovery error: {e}"


def _apply_dream_consequences(agent, dream_data: dict) -> str:
    """
    Extracts narrative and applies stat/relationship osmosis.
    """
    diary_entry = dream_data.get("dream_narrative", "")

    # Robust re-extraction if diary_entry is nested for some reason
    if isinstance(diary_entry, dict):
        diary_entry = diary_entry.get("dream_narrative", str(diary_entry))

    if not diary_entry:
        diary_entry = "I contemplated the void."

    # 1. Stats
    stat_updates = dream_data.get("stat_updates", {})
    if stat_updates:
        logger.info(
            f"[DREAM] Applying stat osmosis for {agent.display_name}: {stat_updates}"
        )
        for stat, delta in stat_updates.items():
            try:
                # Basic cleaning of delta (LLM might send string "+10" despite repair attempt)
                if isinstance(delta, str):
                    delta = int(delta.replace("+", ""))
                agent.soul.update_stat(stat, int(delta))
            except Exception as e:
                logger.warning(f"Failed to update stat {stat}: {e}")

    # 2. Relationships
    rel_updates = dream_data.get("relationship_updates", {})
    if rel_updates:
        logger.info(
            f"[DREAM] Applying relationship osmosis for {agent.display_name}: {list(rel_updates.keys())}"
        )
        for target_name, data in rel_updates.items():
            try:
                delta = int(str(data.get("trust_delta", 0)).replace("+", ""))
                summary = data.get("summary", "")
                hidden_agenda = data.get("hidden_agenda", None)
                if delta != 0 or summary or hidden_agenda:
                    agent.soul.update_relationship(
                        target_name, delta, summary, hidden_agenda
                    )
            except Exception as e:
                logger.warning(f"Failed to update relationship with {target_name}: {e}")

    # 3. Store and Persist
    agent.save_state()
    update_interaction_summaries(agent, diary_entry)

    asyncio.create_task(asyncio.to_thread(_save_dream_memory, agent, diary_entry))

    return diary_entry


async def dream_phase_stream(
    agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None
):
    """
    Wrapper for consistent behavior.
    Even when 'streaming' (via API), we MUST calculate the full dream first to apply stats.
    Then we yield the narrative in chunks to satisfy the API contract.
    """
    # 1. Execute full dream logic (Stats + Memory)
    full_narrative = await dream_phase(agent, raw_chat_log, trust_deltas)

    # 2. Fake stream the result (so the UI gets the typing effect)
    # Yield in chunks of 10 chars
    chunk_size = 10
    for i in range(0, len(full_narrative), chunk_size):
        yield full_narrative[i : i + chunk_size]
        await asyncio.sleep(0.01)  # Small delay for effect


def _prepare_dream_prompts(
    agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None
):
    """
    Constructs the prompt that requests JSON output for Stat Osmosis.
    """
    # 1. Process Logs
    processed_log = []
    for entry in raw_chat_log:
        if isinstance(entry, dict):
            msg_type = entry.get("type")
            content = entry.get("content", "") or entry.get("data", {}).get(
                "public_text", ""
            )
            speaker = (
                entry.get("data", {}).get("name")
                if msg_type == "agent_post"
                else "Chairman"
            )

            if msg_type == "user":
                speaker = "Chairman"
            if msg_type == "user_post":
                speaker = "Chairman (Broadcast)"

            marker = "(YOU)" if speaker == agent.soul.name else ""
            processed_log.append(f"[Speaker: {speaker} {marker}] -> {content}")
        else:
            processed_log.append(str(entry))  # Fallback

    chat_log_str = "\n".join(processed_log)

    # 2. Context Strings
    dynamic_stats_str = str(agent.soul.dynamic_stats)

    relationships_str = ""
    if not trust_deltas:
        trust_deltas = {}

    for name, rel in agent.soul.relationships.items():
        delta = trust_deltas.get(name, 0)
        delta_str = f"{'+' if delta > 0 else ''}{delta}"
        relationships_str += f"  - {name}: Trust={rel.trust_score} (Session Change: {delta_str}). Summary: {rel.last_interaction_summary}\n"

    goals_str = "\n".join(
        [f"  - {g.description}" for g in agent.soul.goals if g.active]
    )

    # 3. Construct System Prompt
    system_prompt = (
        f"You are {agent.soul.name}. Review this session:\n{chat_log_str}\n\n"
        "**CRITICAL: Lines marked '(YOU)' are YOUR OWN actions.**\n\n"
        "TASK: Analyze the session and reflect on your emotional state.\n"
        "1. WRITE A DIARY ENTRY: Pure, emotional prose. No headers.\n"
        "2. DETERMINE STAT CHANGES: How did this session affect your Confidence, Paranoia, Loyalty, and Energy?\n"
        "3. UPDATE RELATIONSHIPS: Did your trust in anyone change? Do you have a new label for them?\n"
        "   - If trust in a peer has dropped below -40 or dropped by >10 this session, define or update your 'hidden_agenda' for them.\n\n"
        "OUTPUT FORMAT: You must output a valid JSON object. Do NOT output markdown blocks.\n"
        "{\n"
        '  "dream_narrative": "Today was difficult. Midas is hiding something...",\n'
        '  "stat_updates": {\n'
        '    "confidence": 5,\n'
        '    "paranoia": 10,\n'
        '    "loyalty_to_chairman": -5,\n'
        '    "stress_level": 5,\n'
        '    "energy": -10\n'
        "  },\n"
        '  "relationship_updates": {\n'
        '    "Agent Name": {\n'
        '      "trust_delta": -15,\n'
        '      "summary": "Suspicious of their motives",\n'
        '      "hidden_agenda": "Monitor their communications for signs of betrayal"\n'
        "    }\n"
        "  }\n"
        "}"
    )
    user_message = "Reflect on the session and generate your dream JSON."

    return system_prompt, user_message


def update_interaction_summaries(agent, session_summary: str):
    """Legacy helper: used as fallback or for secondary summary updates."""
    # This logic is mostly superseded by the JSON 'summary' but kept for robustness
    pass


def _save_dream_memory(agent, text: str):
    """Uses agent.memory to save the narrative.
    FIX BUG-12: Uses agent.agent_name (snake_case ID) for Memory DB consistency."""
    agent_id = agent.agent_name  # 'general_ares' not 'General Ares'
    logger.info(f"[MEMORY] Saving dream to Subjective Memory for {agent_id}.")
    try:
        if hasattr(agent, "memory") and agent.memory:
            agent.memory.save_memory(
                agent_name=agent_id, text=text, emotion="reflection"
            )
        else:
            from memory.store import SubjectiveMemory

            SubjectiveMemory().save_memory(
                agent_name=agent_id, text=text, emotion="reflection"
            )
    except Exception as e:
        logger.error(f"[MEMORY] Failed to save dream memory for {agent_id}: {e}")


async def review_agendas(agent, trust_deltas: Dict[str, int]):
    """
    Refines the agent's goals based on the trust shifts from the session.
    If trust drops significantly, adds a defensive goal.
    If trust rises, might add a cooperative goal.
    FIX BUG-04: Caps active goals at 10 to prevent unbounded growth.
    """
    if not trust_deltas:
        return

    # FIX BUG-04: Count active goals; skip adding if already at cap
    MAX_GOALS = 10
    active_count = sum(1 for g in agent.soul.goals if g.active)

    for target, delta in trust_deltas.items():
        if active_count >= MAX_GOALS:
            logger.info(
                f"[AGENDA] Goal cap ({MAX_GOALS}) reached for {agent.agent_name}. Skipping new goals."
            )
            break

        # High Distrust -> Defensive Goal
        if delta <= -10:
            new_goal = f"Monitor {target} for betrayal"
            # Check if exists
            if not any(g.description == new_goal for g in agent.soul.goals):
                from core.schema import Goal

                agent.soul.goals.append(
                    Goal(
                        description=new_goal,
                        priority="tactical",
                        active=True,
                        progress=0,
                    )
                )
                active_count += 1
                logger.info(
                    f"[AGENDA] Added defensive goal against {target} for {agent.agent_name}"
                )

        # High Trust -> Cooperative Goal
        elif delta >= 15:
            new_goal = f"Strengthen alliance with {target}"
            if not any(g.description == new_goal for g in agent.soul.goals):
                from core.schema import Goal

                agent.soul.goals.append(
                    Goal(
                        description=new_goal,
                        priority="tactical",
                        active=True,
                        progress=0,
                    )
                )
                active_count += 1
                logger.info(
                    f"[AGENDA] Added alliance goal with {target} for {agent.agent_name}"
                )
