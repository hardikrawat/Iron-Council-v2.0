import os
import asyncio
from core.agent import IronAgent
from core.llm import LLMService
from core.dream import dream_phase, review_agendas, update_interaction_summaries
from core.physics import GamemasterPhysics
from memory.store import SubjectiveMemory

def setup_walkthrough():
    """
    Guides the user through setting up the LLM provider.
    """
    print("\n" + "="*40)
    print("--- IRON COUNCIL SETUP WALKTHROUGH ---")
    print("="*40)
    print("1. Cloud APIs (OpenAI / Anthropic)")
    print("2. Local Model (Ollama)")
    
    choice = input("\nSelect your LLM provider (1 or 2): ").strip()
    
    if choice == "1":
        print("\n[Cloud API Setup]")
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            openai_key = input("Enter your OpenAI API Key (or press enter to skip if you have Anthropic): ").strip()
            if openai_key:
                os.environ["OPENAI_API_KEY"] = openai_key
                
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            anthropic_key = input("Enter your Anthropic API Key (or press enter to skip): ").strip()
            if anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            print("Warning: No API keys found. The agents might fail to respond.")
            
    elif choice == "2":
        print("\n[Local Model Setup]")
        url = input("Enter your Local LLM URL (default: http://localhost:11434/api/chat): ").strip()
        if url:
            os.environ["LOCAL_LLM_URL"] = url
        
        model = input("Enter the local model name to use (e.g., llama3, mistral): ").strip()
        if model:
            os.environ["LLM_PROVIDER"] = "local"
            os.environ["LOCAL_MODEL_NAME"] = model
            # We'll override the base_model for all agents for this session
            return model
    else:
        print("Invalid choice. Defaulting to environment configuration.")
    
    return None

def main():
    # Setup Walkthrough
    local_model_override = setup_walkthrough()
    
    # Initialize services
    print("\nInitializing services...")
    llm = LLMService()
    physics = GamemasterPhysics(llm)
    memory_store = SubjectiveMemory()
    
    # Load agents
    agent_names = ["general_ares", "diplomat_dove", "banker_midas", "analyst_logic"]
    print(f"Loading agents: {', '.join(agent_names)}...")
    agents = []
    for name in agent_names:
        agent = IronAgent(name)
        if local_model_override:
            agent.soul.base_model = local_model_override
        agents.append(agent)
    
    session_log = []
    
    # Initialize trust snapshots BEFORE the session loop
    # This captures the baseline for calculating deltas at dream phase
    initial_trust_snapshots = {}
    for agent in agents:
        initial_trust_snapshots[agent.agent_name] = {
            name: rel.trust_score
            for name, rel in agent.soul.relationships.items()
        }
    
    print("\n" + "="*40)
    print("--- IRON COUNCIL SESSION START ---")
    print("="*40)
    print("Type 'end session' to finish and trigger the dream phase.\n")
    
    while True:
        try:
            print("\n" + "="*30)
            user_input = input("Chairman: ").strip()
        except EOFError:
            break
            
        # ROBUST EXIT CHECK
        if user_input.lower() in ["end session", "exit", "quit", "end session."]:
            print("\n🛑 SESSION ENDED. INITIATING SLEEP CYCLE...")
            break
            
        session_log.append(f"Chairman: {user_input}")
        
        all_responses = []  # Collected after ALL speak — for reconciliation
        
        for agent in agents:
            # Recall
            memories = agent.recall_memories(user_input)
            context_string = ""
            if memories:
                context_string = "I remember: " + " | ".join(memories)
            
            # Speak
            response = agent.speak(user_input, context=context_string)
            print(f"\n{agent.soul.name}: {response}")
            session_log.append(f"{agent.soul.name}: {response}")
            
            # Physics — User ↔ Agent ONLY (stats + goals, NO relationships)
            print("--- UPDATING PSYCHE (User↔Agent) ---")
            active_goals = [g.description for g in agent.soul.goals if g.active]
            current_stats = agent.soul.dynamic_stats.model_dump()
            impact = physics.calculate_impact(
                agent.agent_name, current_stats, user_input,
                agent_goals=active_goals
            )
            
            # Apply stat changes (User ↔ Agent)
            agent.soul.update_stat('confidence', impact.get('confidence_change', 0))
            agent.soul.update_stat('paranoia', impact.get('paranoia_change', 0))
            agent.soul.update_stat('loyalty_to_chairman', impact.get('loyalty_change', 0))
            
            # Apply goal progress
            for goal_desc, delta in impact.get('goal_updates', {}).items():
                agent.soul.update_goal_progress(goal_desc, delta)
            completed = agent.soul.check_goal_completion()
            if completed:
                print(f"  🎯 GOAL COMPLETED: {', '.join(completed)}")
            
            agent.save_state()
            print(f" > {agent.agent_name} Impact: {impact}")
            
            # Collect for reconciliation
            all_responses.append({
                "name": agent.soul.name,
                "public_text": response
            })
        
        # Reconciliation — Agent ↔ Agent ONLY (trust deltas)
        print("\n--- RECONCILIATION (Agent↔Agent) ---")
        agent_core_values = {a.soul.name: a.soul.core_values for a in agents}
        trust_matrix = physics.reconcile_turn(all_responses, agent_core_values)
        
        for agent in agents:
            deltas = trust_matrix.get(agent.soul.name, {})
            for target_name, delta in deltas.items():
                agent.soul.update_relationship(target_name, delta)
            agent.save_state()
        
        print(f" > Trust Matrix: {trust_matrix}")
            
    print("\n" + "="*40)
    print("--- DREAMING PHASE ---")
    print("="*40)
    print("Agents are reflecting on the session...\n")
    
    for agent in agents:
        diary_entry = asyncio.run(dream_phase(agent, session_log))
        print(f"[{agent.soul.name}'s Diary Entry]")
        print(diary_entry)
        print("-" * 30 + "\n")
        
        # Review agendas based on trust deltas (compare vs INITIAL baseline)
        snapshot = initial_trust_snapshots.get(agent.agent_name, {})
        deltas = {}
        for name, rel in agent.soul.relationships.items():
            old_score = snapshot.get(name, 0)
            deltas[name] = rel.trust_score - old_score
        
        asyncio.run(review_agendas(agent, deltas))
        agent.save_state()
    
    # Reset trust snapshots after dream phase (for potential next session)
    for agent in agents:
        initial_trust_snapshots[agent.agent_name] = {
            name: rel.trust_score
            for name, rel in agent.soul.relationships.items()
        }

if __name__ == "__main__":
    main()
