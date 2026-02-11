
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
        import datetime
        timestamp = datetime.datetime.now().isoformat()
        await self._append_log({"type": "user", "content": content, "timestamp": timestamp})
        
        logger.info(f"[PHYSICS] Analyzing World Event: {content[:30]}...")

        # Calculate impact for EACH agent
        # We run these concurrently for performance
        tasks = []
        for agent in self.agents:
            tasks.append(self._process_world_event_for_agent(agent, content))
        
        await asyncio.gather(*tasks)

    async def _process_world_event_for_agent(self, agent: IronAgent, content: str):
        try:
            # Broadcast Physics Sync START
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "START", "agent": agent.agent_name, "type": "WORLD_IMPACT"})

            # Physics Calculation - Non-blocking
            impact = await asyncio.to_thread(
                self.physics.calculate_impact,
                content, agent.soul
            )
            
            # Apply Updates
            agent.soul.update_stat('confidence', impact.get('confidence_change', 0))
            agent.soul.update_stat('paranoia', impact.get('paranoia_change', 0))
            agent.soul.update_stat('loyalty_to_chairman', impact.get('loyalty_to_chairman_change', 0))
            agent.soul.update_stat('stress_level', impact.get('stress_level_change', 0))
            
            # Goals
            for goal_desc, delta in impact.get('goal_updates', {}).items():
                agent.soul.update_goal_progress(goal_desc, delta)
            
            agent.save_state()
            
            # Broadcast Stat Update
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": agent.agent_name,
                "status": "STAT_UPDATE",
                "details": "Reaction to World Event",
                "stats": agent.soul.dynamic_stats.model_dump(),
                "goals": [g.model_dump() for g in agent.soul.goals]
            })
            
            # Signal Completion for Reaction Gating
            await self.event_bus.publish(EventType.PHYSICS_COMPLETE, {
                "agent": agent.agent_name,
                "type": "WORLD_EVENT",
                "content": content
            })
            
            logger.info(f"[PHYSICS] Updated {agent.soul.name} stats via World Event.")
            
        except Exception as e:
            logger.error(f"Error processing world event for {agent.soul.name}: {e}")
        finally:
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "END"})

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
        
        import datetime
        # Reuse timestamp if provided in payload, else generate
        timestamp = payload.get("timestamp") or datetime.datetime.now().isoformat()
        
        entry_data = {
            "name": self._get_soul_name(speaker_name), 
            "public_text": content,
            # FIX MAJ-07: Include hidden_text for complete dream phase analysis
            "hidden_text": payload.get("hidden_text", "")
        }
        await self._append_log({"type": "agent_post", "data": entry_data, "timestamp": timestamp})

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
            # Broadcast Physics Sync START
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "START", "agent": listener.agent_name, "type": "REACTION", "target": speaker_name})

            # Fix #9: Resolve agent_id -> soul name so relationships use correct key
            speaker_soul_name = self._get_soul_name(speaker_name)
            
            delta = await asyncio.to_thread(
                self.physics.calculate_relationship_update,
                speaker_soul_name, content, listener
            )
            
            listener.save_state()
            
            # Fix #6: Broadcast relationship change to frontend
            if delta != 0:
                await self.event_bus.publish(EventType.AGENT_STATUS, {
                    "agent": listener.agent_name,
                    "status": "RELATIONSHIP_UPDATE",
                    "details": f"Trust toward {speaker_soul_name}: {delta:+d}",
                    "relationship_data": {
                        "listener": listener.soul.name,
                        "speaker": speaker_soul_name,
                        "delta": delta,
                        "new_score": listener.soul.get_relationship_score(speaker_soul_name)
                    }
                })
            
        except Exception as e:
            logger.error(f"Error processing reaction for {listener.soul.name}: {e}")
        finally:
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "END"})

    def _get_soul_name(self, agent_id: str) -> str:
        for a in self.agents:
            if a.agent_name == agent_id:
                return a.soul.name
        return agent_id
