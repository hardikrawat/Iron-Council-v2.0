import asyncio
import json
import logging
from typing import List, Dict, Optional
from memory.store import SubjectiveMemory

logger = logging.getLogger(__name__)

# Initialize the global memory store
memory_store = SubjectiveMemory()


async def dream_phase(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None) -> str:
    """
    Synthesizes the chat log into a subjective diary entry for the agent (Non-streaming).
    trust_deltas: {"Agent Name": delta_int} — injected so the LLM knows who helped/opposed.
    """
    system_prompt, user_message = _prepare_dream_prompts(agent, raw_chat_log, trust_deltas)
    
    # Generate the diary entry using the agent's LLM service
    diary_entry = await asyncio.to_thread(
        agent.llm.generate_response,
        model_name=agent.soul.base_model,
        system_prompt=system_prompt,
        user_message=user_message
    )
    
    # Update interaction summaries based on this agent's own reflection
    update_interaction_summaries(agent, diary_entry)
    
    _save_dream_memory(agent.soul.name, diary_entry)
    return diary_entry


async def dream_phase_stream(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None):
    """
    Asynchronously streams the subjective diary entry for the agent.
    trust_deltas: {"Agent Name": delta_int} — injected so the LLM knows who helped/opposed.
    """
    system_prompt, user_message = _prepare_dream_prompts(agent, raw_chat_log, trust_deltas)
    
    full_text = ""
    async for chunk in agent.llm.generate_response_stream(
        model_name=agent.soul.base_model,
        system_prompt=system_prompt,
        user_message=user_message
    ):
        full_text += chunk
        yield chunk
    
    # Update interaction summaries based on this agent's own reflection
    update_interaction_summaries(agent, full_text)
    
    # Save the reflection to the agent's memory once complete
    _save_dream_memory(agent.soul.name, full_text)


def _prepare_dream_prompts(agent, raw_chat_log: List, trust_deltas: Optional[Dict[str, int]] = None):
    """
    Prepares the dream prompts with full soul context: stats, relationships, and goals.
    Adds perspective markers to help the agent distinguish its own actions from others.
    Injects trust deltas for conflict-aware dreaming (Phase 2.6).
    """
    # Process chat log with perspective markers
    processed_log = []
    for entry in raw_chat_log:
        if isinstance(entry, str):
            # Legacy string format - try to detect if it's the agent speaking
            if entry.startswith(f"{agent.soul.name}:"):
                processed_log.append(f"[Speaker: {agent.soul.name} (YOU)] -> {entry[len(agent.soul.name)+1:].strip()}")
            else:
                processed_log.append(entry)
        elif isinstance(entry, dict):
            msg_type = entry.get("type")
            if msg_type == "user":
                processed_log.append(f"[Speaker: Chairman] -> {entry.get('content')}")
            elif msg_type == "user_post":
                processed_log.append(f"[Speaker: Chairman (Broadcast)] -> {entry.get('content')}")
            elif msg_type == "agent_post":
                data = entry.get("data", {})
                speaker_name = data.get('name')
                content = data.get('public_text')
                # Mark if this is the agent's own speech
                if speaker_name == agent.soul.name:
                    processed_log.append(f"[Speaker: {speaker_name} (YOU)] -> {content}")
                else:
                    processed_log.append(f"[Speaker: {speaker_name}] -> {content}")
            else:
                processed_log.append(str(entry))
        else:
            processed_log.append(str(entry))

    chat_log_str = "\n".join(processed_log)
    dynamic_stats_str = str(agent.soul.dynamic_stats)
    
    # --- Phase 2.6: Build relationship context with trust deltas ---
    relationships_str = ""
    if trust_deltas is None:
        trust_deltas = {}
    
    for name, rel in agent.soul.relationships.items():
        delta = trust_deltas.get(name, 0)
        # Show current score and recent change
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        if delta != 0:
            if delta > 0:
                label = "Growing alliance"
            elif rel.trust_score < 0:
                label = "Growing hostility"
            else:
                label = "Recent friction"
            rel_desc = f"{name}: trust={rel.trust_score} (delta: {delta_str}) <- {label}"
        else:
            rel_desc = f"{name}: trust={rel.trust_score} (no change)"
        if rel.last_interaction_summary:
            rel_desc += f" (last: {rel.last_interaction_summary})"
        if rel.hidden_agenda:
            rel_desc += f" [AGENDA: {rel.hidden_agenda}]"
        relationships_str += f"  - {rel_desc}\n"
    
    # Build goals context for dreaming
    goals_str = ""
    active_goals = [g for g in agent.soul.goals if g.active]
    if active_goals:
        goals_str = "\n".join(
            f"  - {g.description} ({g.priority}, {g.progress}% complete)"
            for g in active_goals
        )
    
    # --- Phase 2.6: Trust Delta Summary for chain-of-thought ---
    trust_delta_summary = ""
    if trust_deltas:
        delta_lines = []
        for name, delta in trust_deltas.items():
            if delta != 0:
                current_score = agent.soul.get_relationship_score(name)
                delta_lines.append(f"  {name}: {'+' if delta > 0 else ''}{delta} (total now: {current_score})")
        if delta_lines:
            trust_delta_summary = "\nTRUST CHANGES THIS SESSION:\n" + "\n".join(delta_lines) + "\n"
    
    system_prompt = (
        f"You are {agent.soul.name}. Review these events:\n{chat_log_str}\n\n"
        "**CRITICAL: Lines marked '(YOU)' are YOUR OWN actions and words. "
        "Never refer to yourself in the third person. Always use 'I', 'Me', 'My' when discussing your own actions.**\n\n"
        # --- Phase 2.6: Chain-of-Thought for conflict awareness ---
        "BEFORE WRITING, COMPLETE THIS INTERNAL ANALYSIS:\n"
        "Step 1: ANALYZE ALLIANCES\n"
        "- For each council member, check: Did they vote the same way as me?\n"
        "- Look at the Trust Delta. NEGATIVE = they OPPOSED me. POSITIVE = they BACKED me.\n"
        "- If the Trust Delta is negative, this agent is a source of FRICTION or OPPOSITION.\n"
        "- If the Trust Delta is positive, this agent is an ALLY.\n\n"
        "Step 2: CALIBRATE YOUR EMOTIONAL RESPONSE\n"
        "- If Delta is negative but TOTAL trust is still high (above 0): express disappointment or frustration, NOT betrayal.\n"
        "- If Delta is negative AND TOTAL trust is below 0: express suspicion, anger, or hostility.\n"
        "- Only treat them as an ENEMY if the TOTAL trust score is below 0.\n"
        "- Do NOT hallucinate agreement if the Trust Delta is negative.\n\n"
        "Step 3: WRITE DIARY based strictly on Step 1 and Step 2.\n\n"
        # --- End Phase 2.6 injection ---
        f"Your current state is: {dynamic_stats_str}.\n"
        f"Your relationships:\n{relationships_str}"
        f"{trust_delta_summary}"
        f"Your goals:\n{goals_str}\n\n"
        "FORMATTING: Write as pure prose, as if handwritten in a private journal. "
        "Format EXACTLY like this example:\n"
        "'Today was difficult. The Chairman pressured me to reveal my sources, and I could feel "
        "Dove watching me for any sign of weakness. Ares backed me up, surprisingly — his blunt "
        "support carried weight. I need to strengthen our alliance before the next session. "
        "My stress is rising but my resolve remains firm.'\n\n"
        "Do NOT use markdown headers, bold text, bullet points, 'Title:', 'Date:', "
        "'Confidence:', or any stat numbers. Just raw, emotional prose.\n"
        "Do NOT include the analysis steps in your diary. Only write the diary entry itself."
    )
    user_message = "Reflect on the recent events in your diary."
    return system_prompt, user_message


async def review_agendas(agent, trust_deltas: Dict[str, int], llm_service=None):
    """
    Post-dream step: Re-evaluates hidden_agenda for each relationship based on
    trust score changes during the session.
    
    - If trust rose by >10: clear hostile hidden_agenda
    - If trust dropped by >10: generate a new hostile agenda via LLM
    """
    for target_name, delta in trust_deltas.items():
        if target_name not in agent.soul.relationships:
            continue
            
        rel = agent.soul.relationships[target_name]
        
        if delta > 10 and rel.hidden_agenda:
            # Trust improved significantly — drop the hostile agenda
            logger.info(f"[DREAM] {agent.soul.name} clearing agenda against {target_name} (trust +{delta})")
            rel.hidden_agenda = None
            
        elif delta < -10:
            # Trust deteriorated — generate a new hostile agenda
            if llm_service is None:
                llm_service = agent.llm
                
            try:
                agenda_prompt = (
                    f"You are {agent.soul.name} ({agent.soul.archetype}). "
                    f"Your trust in {target_name} has dropped significantly. "
                    f"Your core values are: {', '.join(agent.soul.core_values)}. "
                    f"Current trust: {rel.trust_score}. "
                    "Generate a ONE-LINE hidden agenda against them. "
                    "Be specific and in-character. Output ONLY the agenda text, nothing else."
                )
                
                new_agenda = await asyncio.to_thread(
                    llm_service.generate_response,
                    model_name=agent.soul.base_model,
                    system_prompt="You are a character motivation generator. Output only the agenda text.",
                    user_message=agenda_prompt
                )
                
                # Clean up the response
                new_agenda = new_agenda.strip().strip('"').strip("'")
                if len(new_agenda) > 200:
                    new_agenda = new_agenda[:200]
                    
                rel.hidden_agenda = new_agenda
                logger.info(f"[DREAM] {agent.soul.name} formed new agenda against {target_name}: {new_agenda}")
                
            except Exception as e:
                logger.error(f"Failed to generate agenda for {agent.soul.name} vs {target_name}: {e}")


def update_interaction_summaries(agent, session_summary: str):
    """
    After dreaming, update last_interaction_summary for all relationships
    with a brief note relevant to this session.
    """
    for name, rel in agent.soul.relationships.items():
        if name.lower() in session_summary.lower():
            # Extract a relevant snippet (first mention context)
            idx = session_summary.lower().index(name.lower())
            start = max(0, idx - 50)
            end = min(len(session_summary), idx + len(name) + 100)
            snippet = session_summary[start:end].strip()
            rel.last_interaction_summary = snippet[:150]


def _save_dream_memory(agent_name: str, text: str):
    memory_store.save_memory(
        agent_name=agent_name,
        text=text,
        emotion="reflection"
    )
