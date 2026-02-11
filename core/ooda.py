import asyncio
import logging
import random
import time
from typing import List, Dict, Any, Deque
from collections import deque
from core.event_bus import EventBus, EventType
from core.heartbeat import Heartbeat

from functools import partial

# Import IronAgent for type hinting if possible, or use Any
from core.agent import IronAgent

logger = logging.getLogger("OODA")

class EventBuffer:
    def __init__(self, max_size=10):
        self.buffer: Deque[Dict] = deque(maxlen=max_size)

    def add(self, event: Dict):
        self.buffer.append(event)
    
    def get_recent(self) -> List[Dict]:
        return list(self.buffer)

class OODALoop:
    def __init__(self, agent: IronAgent, event_bus: EventBus, heartbeat: Heartbeat):
        self.agent = agent
        self.event_bus = event_bus
        self.heartbeat = heartbeat
        self.memory = EventBuffer()
        self._running = False
        
        # Subscribe to relevant events with type injection
        self.event_bus.subscribe(EventType.WORLD_EVENT, partial(self._on_event, event_type=EventType.WORLD_EVENT))
        self.event_bus.subscribe(EventType.AGENT_SPEAK, partial(self._on_event, event_type=EventType.AGENT_SPEAK))
        self.event_bus.subscribe(EventType.SILENCE_WARNING, partial(self._on_event, event_type=EventType.SILENCE_WARNING))

    async def _on_event(self, payload: Dict[str, Any], event_type: str = None):
        # Inject type into the record for OODA logic
        event = payload.copy()
        event["type"] = event_type
        self.memory.add(event)

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                logger.info(f"{self.agent.soul.name} OODA loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in {self.agent.soul.name} OODA loop: {e}")
            
            # Randomized sleep to desynchronize agents
            await asyncio.sleep(random.uniform(2.0, 4.0))

    async def _run_cycle(self):
        # 1. OBSERVE (Implicitly done via _on_event subscription updates to memory)
        
        # 2. ORIENT
        stats = self.agent.soul.dynamic_stats
        
        # Energy Check: If too tired, just wait
        if stats.energy < 10:
            logger.debug(f"{self.agent.soul.name} is too tired to act.")
            self.agent.soul.update_stat("energy", 5) # Recharge
            return

        # 3. DECIDE (Thrifty Check)
        should_think = False
        
        # Heuristic A: Recent World Event?
        recent_events = self.memory.get_recent()
        if recent_events and recent_events[-1].get("type") == EventType.WORLD_EVENT:
             should_think = True
        
        # Heuristic B: High Tension/Paranoia?
        if self.heartbeat.global_tension > 50 or stats.paranoia > 80:
             if random.random() < 0.4: # 40% chance to react to tension
                 should_think = True

        # Heuristic C: Random Impulsiveness
        if random.random() < 0.05: # 5% random thought
             should_think = True

        if not should_think:
            return

        # 4. DECIDE (LLM)
        # We need to construct a prompt to ask the agent what to do
        # For Phase 3 MVP, we simplify: if we decided to think, we check if we can speak
        
        # Attempt to acquire lock logic
        if not self.heartbeat.conch.owner:
            # Simple decision: "Should I speak?"
            # In a full impl, we'd ask LLM: "Events: [...]. Action: [WAIT, SPEAK]"
            # Here we assume if 'should_think' is true, they WANT to speak.
            
            acquired = self.heartbeat.conch.acquire(self.agent.agent_name)
            if acquired:
                try:
                    # 5. ACT
                    # Generate response using existing agent logic
                    # We need to pass recent context
                    context_str = str(recent_events[-3:]) # Last 3 events
                    
                    response = await asyncio.to_thread(
                        self.agent.speak, "The floor is open.", context_str
                    )
                    
                    # Publish
                    await self.event_bus.publish(EventType.AGENT_SPEAK, {
                        "agent": self.agent.agent_name,
                        "content": response
                    })
                    
                    # Deduct Energy
                    self.agent.soul.update_stat("energy", -10)
                    self.heartbeat.register_activity()
                    
                finally:
                    self.heartbeat.conch.release(self.agent.agent_name)
