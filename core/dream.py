from typing import List
from memory.store import SubjectiveMemory

# Initialize the global memory store
memory_store = SubjectiveMemory()

async def dream_phase(agent, raw_chat_log: List[str]) -> str:
    """
    Synthesizes the chat log into a subjective diary entry for the agent (Non-streaming).
    """
    system_prompt, user_message = _prepare_dream_prompts(agent, raw_chat_log)
    
    # Generate the diary entry using the agent's LLM service
    diary_entry = await asyncio.to_thread(
        agent.llm.generate_response,
        model_name=agent.soul.base_model,
        system_prompt=system_prompt,
        user_message=user_message
    )
    
    _save_dream_memory(agent.soul.name, diary_entry)
    return diary_entry

async def dream_phase_stream(agent, raw_chat_log: List[str]):
    """
    Asynchronously streams the subjective diary entry for the agent.
    """
    system_prompt, user_message = _prepare_dream_prompts(agent, raw_chat_log)
    
    full_text = ""
    async for chunk in agent.llm.generate_response_stream(
        model_name=agent.soul.base_model,
        system_prompt=system_prompt,
        user_message=user_message
    ):
        full_text += chunk
        yield chunk
        
    # Save the reflection to the agent's memory once complete
    _save_dream_memory(agent.soul.name, full_text)

def _prepare_dream_prompts(agent, raw_chat_log: List[str]):
    # Construct the subjective prompt
    processed_log = []
    for entry in raw_chat_log:
        if isinstance(entry, str):
            processed_log.append(entry)
        elif isinstance(entry, dict):
            # Handle visual layout log format
            msg_type = entry.get("type")
            if msg_type == "user":
                processed_log.append(f"Chairman: {entry.get('content')}")
            elif msg_type == "user_post":
                processed_log.append(f"Chairman (Broadcast): {entry.get('content')}")
            elif msg_type == "agent_post":
                data = entry.get("data", {})
                processed_log.append(f"{data.get('name')}: {data.get('public_text')}")
            else:
                # Fallback for other dict types
                processed_log.append(str(entry))
        else:
            processed_log.append(str(entry))

    chat_log_str = "\n".join(processed_log)
    dynamic_stats_str = str(agent.soul.dynamic_stats)
    
    system_prompt = (
        f"You are {agent.soul.name}. Review these events:\n{chat_log_str}\n\n"
        "Write a short diary entry about this. Do NOT be objective.\n"
        "Focus on: Who wronged you? Who helped you? How does this affect your goals?\n"
        f"Your current state is: {dynamic_stats_str}."
    )
    user_message = "Reflect on the recent events in your diary."
    return system_prompt, user_message

def _save_dream_memory(agent_name: str, text: str):
    memory_store.save_memory(
        agent_name=agent_name,
        text=text,
        emotion="reflection"
    )

import asyncio

