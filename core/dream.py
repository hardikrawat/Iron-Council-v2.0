from typing import List
from memory.store import SubjectiveMemory

# Initialize the global memory store
memory_store = SubjectiveMemory()

def dream_phase(agent, raw_chat_log: List[str]) -> str:
    """
    Synthesizes the chat log into a subjective diary entry for the agent.
    """
    # Construct the subjective prompt
    chat_log_str = "\n".join(raw_chat_log)
    dynamic_stats_str = str(agent.soul.dynamic_stats)
    
    system_prompt = (
        f"You are {agent.soul.name}. Review these events:\n{chat_log_str}\n\n"
        "Write a short diary entry about this. Do NOT be objective.\n"
        "Focus on: Who wronged you? Who helped you? How does this affect your goals?\n"
        f"Your current state is: {dynamic_stats_str}."
    )
    
    # Generate the diary entry using the agent's LLM service
    diary_entry = agent.llm.generate_response(
        model_name=agent.soul.base_model,
        system_prompt=system_prompt,
        user_message="Reflect on the recent events in your diary."
    )
    
    # Save the reflection to the agent's memory
    memory_store.save_memory(
        agent_name=agent.soul.name,
        text=diary_entry,
        emotion="reflection"
    )
    
    return diary_entry
