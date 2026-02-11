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
        self._running = False
        self._last_processed_world_event = None  # Fix #3: track processed chairman messages
        self._last_processed_agent_event = None  # Fix #16: track processed agent messages

        
        # Subscribe to relevant events with type injection
        self.event_bus.subscribe(EventType.WORLD_EVENT, partial(self._on_event, event_type=EventType.WORLD_EVENT))
        self.event_bus.subscribe(EventType.AGENT_SPEAK, partial(self._on_event, event_type=EventType.AGENT_SPEAK))
        self.event_bus.subscribe(EventType.SILENCE_WARNING, partial(self._on_event, event_type=EventType.SILENCE_WARNING))
        # Fix #9: Subscribe to AGENT_STATUS for Interoception (feeling stat changes)
        self.event_bus.subscribe(EventType.AGENT_STATUS, partial(self._on_event, event_type=EventType.AGENT_STATUS))

    async def _on_event(self, payload: Dict[str, Any], event_type: str = None):
        # Inject type into the record for OODA logic
        event = payload.copy()
        event["type"] = event_type
        
        # Filter AGENT_STATUS: Only care about MY status updates (Internal Sense)
        if event_type == EventType.AGENT_STATUS:
            if event.get("agent") != self.agent.agent_name:
                return # Ignore other agents' internal stats
            if event.get("status") not in ["STAT_UPDATE", "RELATIONSHIP_UPDATE"]:
                return # Ignore routine state changes like "THINKING"

        self.memory.add(event)

    def _format_context(self, events: List[Dict]) -> str:
        """Fix #3: Build readable context from recent events instead of raw dict dump."""
        lines = []
        for e in events:
            etype = e.get("type", "")
            if etype == EventType.WORLD_EVENT:
                lines.append(f'Chairman said: "{e.get("content", "")}"')
            elif etype == EventType.AGENT_SPEAK:
                agent_id = e.get("agent", "Unknown")
                # Try to resolve to soul name
                soul_name = agent_id
                for key, val in [("soul_name", None)]:
                    if key in e:
                        soul_name = e[key]
                lines.append(f'{soul_name} said: "{e.get("content", "")}"')
            elif etype == EventType.SILENCE_WARNING:
                lines.append(f'[The council has been silent for {int(e.get("duration", 0))}s. Tension is rising.]')
            elif etype == EventType.AGENT_STATUS:
                # Interoception: Internal monologue about state changes
                details = e.get("details", "")
                lines.append(f'[INTERNAL SENSE]: {details}')
        return "\n".join(lines) if lines else "No recent activity."

    def _extract_situation(self, events: List[Dict]) -> str:
        """
        Fix #3: Extract the most recent meaningful event (Chairman OR Agent) as the situation.
        """
        for e in reversed(events):
            if e.get("type") == EventType.WORLD_EVENT:
                return f'The Chairman addressed the council: "{e.get("content", "")}"'
            elif e.get("type") == EventType.AGENT_SPEAK:
                speaker = e.get("agent", "Unknown")
                if speaker != self.agent.agent_name:
                    return f'{speaker} just said: "{e.get("content", "")}"'
        
        return "The floor is open. Speak if you have something to contribute."

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
        # 0. Broadcast Start
        await self.event_bus.publish(EventType.AGENT_STATUS, {
            "agent": self.agent.agent_name,
            "status": "OBSERVING",
            "phase": "O",
            "details": "Scanning environment..."
        })

        # 1. OBSERVE (Implicitly done via _on_event subscription updates to memory)
        
        # 2. ORIENT
        await self.event_bus.publish(EventType.AGENT_STATUS, {
            "agent": self.agent.agent_name,
            "status": "ORIENTING",
            "phase": "O",
            "details": "Checking internal vitals..."
        })
        stats = self.agent.soul.dynamic_stats
        
        # Fix #8: Passive energy regeneration every cycle (+2)
        if stats.energy < 100:
            self.agent.soul.update_stat("energy", 2)
        
        # Energy Check: If too tired, just wait
        if stats.energy < 10:
            logger.debug(f"{self.agent.soul.name} is too tired to act.")
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": self.agent.agent_name,
                "status": "RECHARGING",
                "details": "Energy critical. Resting."
            })
            self.agent.soul.update_stat("energy", 10)  # Fix #8: meaningful recharge
            return

        # 3. DECIDE (Thrifty Check)
        await self.event_bus.publish(EventType.AGENT_STATUS, {
            "agent": self.agent.agent_name,
            "status": "DECIDING",
            "phase": "D",
            "details": "Weighing options..."
        })
        should_think = False
        
        # Fix #3: Check if ANY recent event is an unprocessed WORLD_EVENT (not just the last one)
        recent_events = self.memory.get_recent()
        for e in recent_events:
            if e.get("type") == EventType.WORLD_EVENT:
                event_content = e.get("content", "")
                if event_content != self._last_processed_world_event:
                    should_think = True
                    self._last_processed_world_event = event_content
                    break
            
            # Fix #16: Check for AGENT_SPEAK to trigger responsiveness
            if e.get("type") == EventType.AGENT_SPEAK:
                 speaker = e.get("agent")
                 if speaker != self.agent.agent_name: # Don't reply to self
                     content = e.get("content", "")
                     # Unique ID for this event to prevent loops (simulated by content check for now)
                     if content != self._last_processed_agent_event:
                         # Probability check for responsiveness (70% chance to reply to a peer)
                         if random.random() < 0.7:
                             should_think = True
                             self._last_processed_agent_event = content
                             logger.info(f"{self.agent.soul.name} decided to reply to {speaker}.")
                             break
        
        # Heuristic B: High Tension/Paranoia?
        if self.heartbeat.global_tension > 50 or stats.paranoia > 80:
             if random.random() < 0.4: # 40% chance to react to tension
                 should_think = True

        # Heuristic C: Random Impulsiveness
        if random.random() < 0.05: # 5% random thought
             should_think = True

        if not should_think:
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": self.agent.agent_name,
                "status": "IDLE",
                "details": "Standing by."
            })
            return

        # 4. DECIDE (LLM)
        # Attempt to acquire lock logic
        if not self.heartbeat.conch.owner:
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": self.agent.agent_name,
                "status": "WAITING_FOR_LOCK",
                "phase": "A",
                "details": "Attempting to claim the floor..."
            })

            acquired = self.heartbeat.conch.acquire(self.agent.agent_name)
            if acquired:
                try:
                    # 5. ACT
                    # Fix #3: Build readable context and extract chairman message as situation
                    context_str = self._format_context(recent_events[-5:])
                    situation = self._extract_situation(recent_events)
                    
                    # Fix #4: Recall subjective memories before speaking
                    try:
                        memory_query = situation[:200]  # Use situation as query
                        memories = await asyncio.to_thread(
                            self.agent.recall_memories, memory_query
                        )
                        if memories:
                            memory_str = "\n".join(f"- {m}" for m in memories)
                            context_str = f"Your memories:\n{memory_str}\n\nRecent events:\n{context_str}"
                    except Exception as mem_err:
                        logger.warning(f"Memory recall failed for {self.agent.soul.name}: {mem_err}")
                    
                    await self.event_bus.publish(EventType.AGENT_STATUS, {
                        "agent": self.agent.agent_name,
                        "status": "THINKING",
                        "phase": "A",
                        "details": "Formulating response..."
                    })

                    response_data = await asyncio.to_thread(
                        self.agent.speak, situation, context_str
                    )
                    
                    # Fix #14: Unpack dictionary response
                    if isinstance(response_data, dict):
                        public_text = response_data.get("public_text", "")
                        hidden_text = response_data.get("hidden_text", "")
                    else:
                        public_text = str(response_data)
                        hidden_text = ""

                    # Publish with hidden text
                    await self.event_bus.publish(EventType.AGENT_SPEAK, {
                        "agent": self.agent.agent_name,
                        "content": public_text,
                        "hidden_text": hidden_text
                    })
                    
                    await self.event_bus.publish(EventType.AGENT_STATUS, {
                        "agent": self.agent.agent_name,
                        "status": "ACTING",
                        "phase": "A",
                        "details": "Speaking via WebSocket bridge."
                    })
                    
                    # Deduct Energy
                    self.agent.soul.update_stat("energy", -10)
                    self.agent.save_state()  # Fix #7: persist state after OODA changes
                    self.heartbeat.register_activity()
                    
                finally:
                    self.heartbeat.conch.release(self.agent.agent_name)
