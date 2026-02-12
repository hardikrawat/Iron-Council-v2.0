import asyncio
import json
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

async def dream_phase(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None) -> str:
    """
    Synthesizes the chat log into a subjective diary entry, effectively 'dreaming'.
    
    STAT OSMOSIS:
    It generates a JSON response containing:
    1. The dream narrative (Subjective Memory)
    2. Stat updates (Confidence, Paranoia, etc.)
    3. Relationship updates (Trust deltas + New Labels)
    
    Reflects the agent's internal state change back into their Soul.
    """
    system_prompt, user_message = _prepare_dream_prompts(agent, raw_chat_log, trust_deltas)
    
    if agent.event_bus:
        from core.event_bus import EventType
        # Signal that dreaming has started (this might trigger UI effects)
        agent.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {"agent": agent.agent_name, "step": "DREAM_SYNTHESIS"})

    logger.info(f"[DREAM] Synthesizing dream for {agent.agent_name}...")
    
    # 1. Generate Dream (Wait for full JSON)
    try:
        response_text = await asyncio.to_thread(
            agent.llm.generate_response,
            model_name=agent.soul.base_model,
            system_prompt=system_prompt,
            user_message=user_message
        )
    except Exception as e:
        logger.error(f"[DREAM] LLM generation failed: {e}")
        return "I sleep without dreams."

    # 2. Parse & Repair JSON
    try:
        # STRIP CLEANING: Remove inline comments before attempting to parse
        # This fixes issues where local models include the comments from the prompt in the output
        cleaned_text = re.sub(r'//.*', '', response_text)
        
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
        else:
            cleaned_text = cleaned_text.strip()
            # Attempt to find JSON start/end if surrounded by text
            json_start = cleaned_text.find("{")
            json_end = cleaned_text.rfind("}")
            if json_start != -1 and json_end != -1:
                cleaned_text = cleaned_text[json_start:json_end+1]

        dream_data = json.loads(cleaned_text)
    except json.JSONDecodeError:
        logger.error(f"[DREAM] Failed to parse JSON for {agent.agent_name}. Text: {response_text[:100]}...")
        # Fallback: Assume the text IS the narrative, no stats.
        dream_data = {"dream_narrative": response_text}

    # Extract Data
    diary_entry = dream_data.get("dream_narrative", "")
    
    # FIX BUG-2: If diary_entry is still raw JSON (parse fallback used the whole response),
    # attempt to re-extract the actual narrative from it
    if diary_entry and diary_entry.strip().startswith("{"):
        try:
            nested = json.loads(diary_entry)
            diary_entry = nested.get("dream_narrative", diary_entry)
        except (json.JSONDecodeError, TypeError):
            # Last resort: strip everything that looks like JSON structure
            import re as _re
            narrative_match = _re.search(r'"dream_narrative"\s*:\s*"(.*?)"', diary_entry, _re.DOTALL)
            if narrative_match:
                diary_entry = narrative_match.group(1)
    
    if not diary_entry:
         diary_entry = "I contemplated the void." # Safety fallback

    stat_updates = dream_data.get("stat_updates", {})
    rel_updates = dream_data.get("relationship_updates", {})

    # 3. Apply Stat Osmosis (State Updates)
    try:
        if stat_updates:
            logger.info(f"[DREAM] Applying stat osmosis for {agent.agent_name}: {stat_updates}")
            for stat, delta in stat_updates.items():
                try:
                    # Map JSON keys to Soul keys if needed, but schema matches mostly
                    # 'loyalty_to_chairman_change' vs 'loyalty_to_chairman'
                    # The prompt asks for 'loyalty_to_chairman'
                    agent.soul.update_stat(stat, int(delta))
                except Exception as e:
                    logger.warning(f"Failed to update stat {stat}: {e}")

        if rel_updates:
            logger.info(f"[DREAM] Applying relationship osmosis for {agent.agent_name}: {list(rel_updates.keys())}")
            for target_name, data in rel_updates.items():
                try:
                    delta = int(data.get("trust_delta", 0))
                    summary = data.get("new_summary", "")
                    # Only update if there's a change
                    if delta != 0 or summary:
                        agent.soul.update_relationship(target_name, delta, summary)
                        # Also clear old agendas if trust improved significantly?
                        # This logic replaces 'review_agendas'
                        if delta > 10 and agent.soul.relationships[target_name].hidden_agenda:
                             agent.soul.relationships[target_name].hidden_agenda = None
                             logger.info(f"[DREAM] Cleared hostile agenda against {target_name}")

                except Exception as e:
                    logger.warning(f"Failed to update relationship with {target_name}: {e}")

        # Persist to Disk
        agent.save_state()

        # Update interaction summaries (Legacy/Fallback)
        update_interaction_summaries(agent, diary_entry)

    except Exception as e:
        logger.error(f"[DREAM] Error applying dream consequences: {e}")

    # 4. Save to Memory (For Morning Reflection)
    try:
        await asyncio.to_thread(_save_dream_memory, agent, diary_entry)
    except Exception as e:
        logger.error(f"[DREAM] Failed to save memory: {e}")

    return diary_entry


async def dream_phase_stream(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None):
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
        yield full_narrative[i:i+chunk_size]
        await asyncio.sleep(0.01) # Small delay for effect


def _prepare_dream_prompts(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None):
    """
    Constructs the prompt that requests JSON output for Stat Osmosis.
    """
    # 1. Process Logs
    processed_log = []
    for entry in raw_chat_log:
        if isinstance(entry, dict):
            msg_type = entry.get("type")
            content = entry.get("content", "") or entry.get("data", {}).get("public_text", "")
            speaker = entry.get("data", {}).get("name") if msg_type == "agent_post" else "Chairman"
            
            if msg_type == "user": speaker = "Chairman"
            if msg_type == "user_post": speaker = "Chairman (Broadcast)"

            marker = "(YOU)" if speaker == agent.soul.name else ""
            processed_log.append(f"[Speaker: {speaker} {marker}] -> {content}")
        else:
             processed_log.append(str(entry)) # Fallback

    chat_log_str = "\n".join(processed_log)

    # 2. Context Strings
    dynamic_stats_str = str(agent.soul.dynamic_stats)
    
    relationships_str = ""
    if not trust_deltas: trust_deltas = {}
    
    for name, rel in agent.soul.relationships.items():
        delta = trust_deltas.get(name, 0)
        delta_str = f"{'+' if delta > 0 else ''}{delta}"
        relationships_str += f"  - {name}: Trust={rel.trust_score} (Session Change: {delta_str}). Summary: {rel.last_interaction_summary}\n"

    goals_str = "\n".join([f"  - {g.description}" for g in agent.soul.goals if g.active])

    # 3. Construct System Prompt
    system_prompt = (
        f"You are {agent.soul.name}. Review this session:\n{chat_log_str}\n\n"
        "**CRITICAL: Lines marked '(YOU)' are YOUR OWN actions.**\n\n"
        "TASK: Analyze the session and reflect on your emotional state.\n"
        "1. WRITE A DIARY ENTRY: Pure, emotional prose. No headers.\n"
        "2. DETERMINE STAT CHANGES: How did this session affect your Confidence, Paranoia, Loyalty, and Energy?\n"
        "3. UPDATE RELATIONSHIPS: Did your trust in anyone change? Do you have a new label for them?\n\n"
        "OUTPUT FORMAT: You must output a valid JSON object. Do NOT output markdown blocks.\n"
        "{\n"
        '  "dream_narrative": "Today was difficult. Midas is hiding something...",\n'
        '  "stat_updates": {\n'
        '    "confidence": 5,\n'
        '    "paranoia": 10,\n'
        '    "loyalty_to_chairman": -5,\n'
        '    "stress_level": 5,\n'
        '    "energy": -10\n'
        '  },\n'
        '  "relationship_updates": {\n'
        '    "Agent Name": {\n'
        '      "trust_delta": -15,\n'
        '      "new_summary": "Suspicious of their motives"\n'
        '    }\n'
        '  }\n'
        "}"
    )
    user_message = "Reflect on the session and generate your dream JSON."
    
    return system_prompt, user_message


def update_interaction_summaries(agent, session_summary: str):
    """Legacy helper: used as fallback or for secondary summary updates."""
    # This logic is mostly superseded by the JSON 'new_summary' but kept for robustness
    pass 


def _save_dream_memory(agent, text: str):
    """Uses agent.memory to save the narrative.
    FIX BUG-12: Uses agent.agent_name (snake_case ID) for ChromaDB consistency."""
    agent_id = agent.agent_name  # 'general_ares' not 'General Ares'
    logger.info(f"[MEMORY] Saving dream to Subjective Memory for {agent_id}.")
    try:
        if hasattr(agent, 'memory') and agent.memory:
            agent.memory.save_memory(
                agent_name=agent_id,
                text=text,
                emotion="reflection"
            )
        else:
            from memory.store import SubjectiveMemory
            SubjectiveMemory().save_memory(
                agent_name=agent_id,
                text=text,
                emotion="reflection"
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
            logger.info(f"[AGENDA] Goal cap ({MAX_GOALS}) reached for {agent.agent_name}. Skipping new goals.")
            break

        # High Distrust -> Defensive Goal
        if delta <= -10:
            new_goal = f"Monitor {target} for betrayal"
            # Check if exists
            if not any(g.description == new_goal for g in agent.soul.goals):
                from core.schema import Goal
                agent.soul.goals.append(Goal(description=new_goal, priority="tactical", active=True, progress=0))
                active_count += 1
                logger.info(f"[AGENDA] Added defensive goal against {target} for {agent.agent_name}")
        
        # High Trust -> Cooperative Goal
        elif delta >= 15:
            new_goal = f"Strengthen alliance with {target}"
            if not any(g.description == new_goal for g in agent.soul.goals):
                from core.schema import Goal
                agent.soul.goals.append(Goal(description=new_goal, priority="tactical", active=True, progress=0))
                active_count += 1
                logger.info(f"[AGENDA] Added alliance goal with {target} for {agent.agent_name}")
