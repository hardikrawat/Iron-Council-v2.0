
import asyncio
import logging
from typing import Dict, List, Any
from core.event_bus import EventBus, EventType
from core.physics import GamemasterPhysics
from core.agent import IronAgent

logger = logging.getLogger("PhysicsSystem")

class PhysicsSystem:
    """
    The bridge between the EventBus and the GamemasterPhysics engine.
    Listens for events and triggers stat updates in real-time.
    
    Guardrails:
    1. Dream Data Gap: Maintains a 'transcript' of all events for dream.py.
    2. Reaction Spiral: ONLY updates internal state. NEVER triggers output/events.
    """
    def __init__(self, event_bus: EventBus, physics: GamemasterPhysics, agents: List[IronAgent], transcript: List[Dict[str, Any]], on_update=None):
        self.event_bus = event_bus
        self.physics = physics
        self.agents = agents
        self.transcript = transcript # Shared reference to server.py's logs
        self.on_update = on_update   # Callback to save history

    async def start(self):
        """
        Subscribes to relevant events.
        """
        self.event_bus.subscribe(EventType.WORLD_EVENT, self.on_world_event)
        self.event_bus.subscribe(EventType.AGENT_SPEAK, self.on_agent_speak)
        logger.info("PhysicsSystem started and listening.")

    async def _append_log(self, entry: Dict[str, Any]):
        self.transcript.append(entry)
        if self.on_update:
            self.on_update()

    async def on_world_event(self, payload: Dict[str, Any]):
        """
        User/System Action -> Update Agent Stats (Confidence, Paranoia, etc.)
        """
        content = payload.get("content", "")
        # Log to transcript
        await self._append_log({"type": "user", "content": content})
        
        logger.info(f"[PHYSICS] Analyzing World Event: {content[:30]}...")

        # Calculate impact for EACH agent
        # We run these concurrently for performance
        tasks = []
        for agent in self.agents:
            tasks.append(self._process_world_event_for_agent(agent, content))
        
        await asyncio.gather(*tasks)

    async def _process_world_event_for_agent(self, agent: IronAgent, content: str):
        try:
            active_goals = [g.description for g in agent.soul.goals if g.active]
            current_stats = agent.soul.dynamic_stats.model_dump()
            
            # Physics Calculation
            # Note: calculate_impact is blocking (calls LLM), so we might want to run in thread
            # if not already async. calculate_impact uses llm_service.generate_response which is sync.
            # So we wrap in to_thread.
            impact = await asyncio.to_thread(
                self.physics.calculate_impact,
                agent.agent_name, current_stats, content, active_goals
            )
            
            # Apply Updates
            agent.soul.update_stat('confidence', impact.get('confidence_change', 0))
            agent.soul.update_stat('paranoia', impact.get('paranoia_change', 0))
            agent.soul.update_stat('loyalty_to_chairman', impact.get('loyalty_change', 0))
            
            # Goals
            for goal_desc, delta in impact.get('goal_updates', {}).items():
                agent.soul.update_goal_progress(goal_desc, delta)
            
            agent.save_state()
            logger.info(f"[PHYSICS] Updated {agent.soul.name} stats via World Event.")
            
        except Exception as e:
            logger.error(f"Error processing world event for {agent.soul.name}: {e}")

    async def on_agent_speak(self, payload: Dict[str, Any]):
        """
        Agent Speaks -> Update OTHER Agents' Trust (Relationship Update)
        """
        speaker_name = payload.get("agent", "")
        content = payload.get("content", "")
        
        # Log to transcript (reformatting to match dream.py expectations if needed, 
        # but storing raw payload is usually safer, dream.py handles formatting)
        # Note: server.py bridge constructs the full "data" payload. 
        # But payload received here might be simpler? 
        # Bridge publishes: EventType.AGENT_SPEAK, {...simple...} ???
        # Wait, core/ooda.py publishes: "agent": self.agent.agent_name, "content": response.
        # PhysicsSystem receives that. 
        # Appends formatted entry.
        
        entry_data = {
            "name": self._get_soul_name(speaker_name), 
            "public_text": content
        }
        await self._append_log({"type": "agent_post", "data": entry_data})

        if not speaker_name:
            return

        logger.info(f"[PHYSICS] Analyzing Speech by {speaker_name}...")

        tasks = []
        for listener in self.agents:
            if listener.agent_name == speaker_name:
                continue # Don't react to self
            
            tasks.append(self._process_reaction(listener, speaker_name, content))
        
        await asyncio.gather(*tasks)

    async def _process_reaction(self, listener: IronAgent, speaker_name: str, content: str):
        try:
            # We need the speaker's soul name for the prompt, easier if passed, 
            # but we can resolve it or just pass speaker_name (agent ID) to physics, 
            # physics usually expects Agent Names (Soul Names) or IDs? 
            # existing physics.reconcile_turn uses "name" which is typically soul name.
            # let's assume usage of agent_name (ID) for consistency, or map it.
            
            # Refactored physics.calculate_relationship_update will be implemented to take:
            # speaker_name, content, listener_agent
            
            await asyncio.to_thread(
                self.physics.calculate_relationship_update,
                speaker_name, content, listener
            )
            
            # Checks and generic updates are done inside calculate_relationship_update or we do them here.
            # The Requirement says: "Update listener_agent.soul.relationships[speaker_name].trust_score"
            # It's cleaner if Physics engine returns the delta, and WE apply it here.
            # But the user prompt said "Trigger a new method... Calculate impact... Update soul state".
            # Let's say physics method applies it or returns it. I'll make it return delta for modularity,
            # but modify the agent inside if requested.
            # "Refactor physics.py ... Update listener_agent... " implies method does it. 
            # I will follow that.
            
            listener.save_state()
            
        except Exception as e:
            logger.error(f"Error processing reaction for {listener.soul.name}: {e}")

    def _get_soul_name(self, agent_id: str) -> str:
        for a in self.agents:
            if a.agent_name == agent_id:
                return a.soul.name
        return agent_id
