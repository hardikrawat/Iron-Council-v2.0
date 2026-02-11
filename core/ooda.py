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
    def __init__(self, max_size=50): # Fix #2: Increased buffer size
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
        self._last_processed_world_event = None  # Fix #3: track processed chairman messages
        self._last_processed_agent_event = None  # Fix #16: track processed agent messages
        self._consecutive_errors = 0 # Fix: Track repeated failures
        self._waiting_for_physics = False # Fix #99: Reaction Gating
        self._physics_wait_start = 0

        
        # Subscribe to relevant events with type injection
        # FIX MAJ-08: Store callbacks as instance refs so we can unsubscribe on stop
        self._sub_world = partial(self._on_event, event_type=EventType.WORLD_EVENT)
        self._sub_speak = partial(self._on_event, event_type=EventType.AGENT_SPEAK)
        self._sub_silence = partial(self._on_event, event_type=EventType.SILENCE_WARNING)
        self._sub_status = partial(self._on_event, event_type=EventType.AGENT_STATUS)
        self._sub_physics = partial(self._on_event, event_type=EventType.PHYSICS_COMPLETE)

        self.event_bus.subscribe(EventType.WORLD_EVENT, self._sub_world)
        self.event_bus.subscribe(EventType.AGENT_SPEAK, self._sub_speak)
        self.event_bus.subscribe(EventType.SILENCE_WARNING, self._sub_silence)
        self.event_bus.subscribe(EventType.AGENT_STATUS, self._sub_status)
        self.event_bus.subscribe(EventType.PHYSICS_COMPLETE, self._sub_physics)

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

        # Fix #2: Filter Silence Events from buffer to prevent amnesia
        # We handle silence via global tension check in _run_cycle instead
        if event_type == EventType.SILENCE_WARNING:
            return

        # Fix #99: Handle Physics Gating
        if event_type == EventType.WORLD_EVENT:
            self._waiting_for_physics = True
            self._physics_wait_start = time.time()
            logger.info(f"{self.agent.soul.name} detected World Event. Waiting for emotional impact...")
        
        # FIX CRIT/ARCH-01: Also gate on AGENT_SPEAK to prevent Race Condition
        if event_type == EventType.AGENT_SPEAK:
            speaker = event.get("agent")
            if speaker != self.agent.agent_name: # Don't wait for self
                self._waiting_for_physics = True
                self._physics_wait_start = time.time()
                # logger.debug(f"{self.agent.soul.name} detected speech by {speaker}. Waiting for trust update.")

        if event_type == EventType.PHYSICS_COMPLETE or event_type == EventType.AGENT_STATUS:
             # Check for Physics complete OR Relationship Update
             is_physics = event_type == EventType.PHYSICS_COMPLETE and event.get("agent") == self.agent.agent_name
             is_rel_update = event_type == EventType.AGENT_STATUS and event.get("status") == "RELATIONSHIP_UPDATE" and event.get("agent") == self.agent.agent_name
             
             if is_physics or is_rel_update:
                if self._waiting_for_physics:
                     self._waiting_for_physics = False
                     logger.info(f"{self.agent.soul.name} processed physics/relationship update. Ready to respond.")
                return # Don't need to add this control signal to memory

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
            elif etype == EventType.AGENT_STATUS:
                # Interoception: Internal monologue about state changes
                details = e.get("details", "")
                lines.append(f'[INTERNAL SENSE]: {details}')
        
        # Fix #2: Synthesize Atmosphere from Global Tension
        if self.heartbeat.global_tension > 20:
             lines.append(f'[Atmosphere: The council is silent. Tension is at {self.heartbeat.global_tension}%.]')
             
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
                # Success - reset errors
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                logger.info(f"{self.agent.soul.name} OODA loop cancelled.")
                break
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"Error in {self.agent.soul.name} OODA loop (Attempt {self._consecutive_errors}): {e}")
                
                # Backoff Strategy
                if self._consecutive_errors > 5:
                    logger.critical(f"{self.agent.soul.name} is COMATOSE due to repeated errors. Sleeping for 60s.")
                    await asyncio.sleep(60)
                    self._consecutive_errors = 0 # Try to wake up eventually
                else:
                    await asyncio.sleep(2 ** self._consecutive_errors) # 2, 4, 8, 16, 32s
            
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
        
        # Fix #99: Reaction Gating Check
        if self._waiting_for_physics:
             # Safety timeout (5s)
             if time.time() - self._physics_wait_start > 5.0:
                 self._waiting_for_physics = False
                 logger.warning(f"{self.agent.soul.name} timed out waiting for physics. Proceeding anyway.")
             else:
                 await self.event_bus.publish(EventType.AGENT_STATUS, {
                    "agent": self.agent.agent_name,
                    "status": "FEELING",
                    "details": "Processing emotional impact..."
                 })
                 logger.info(f"{self.agent.soul.name} [OODA] -> Gated by Physics. Waiting for emotional impact.")
                 return # Skip this cycle, wait for physics

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
            logger.info(f"{self.agent.soul.name} [OODA: ORIENT] -> Energy critical ({stats.energy}). Resting to recharge.")
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
        decision_trigger = None # To track what triggered the decision
        
        # Fix #3: Check if ANY recent event is an unprocessed WORLD_EVENT (not just the last one)
        recent_events = self.memory.get_recent()
        for e in recent_events:
            if e.get("type") == EventType.WORLD_EVENT:
                event_content = e.get("content", "")
                if event_content != self._last_processed_world_event:
                    should_think = True
                    decision_trigger = ("WORLD", event_content)
                    logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Triggered by World Event: '{event_content[:50]}...'")
                    # NOTE: Do NOT update _last_processed_world_event yet! Wait for Act phase.
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
                                 decision_trigger = ("AGENT", content)
                                 # NOTE: Do NOT update _last_processed_agent_event yet!
                                 logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Triggered by peer {speaker}: '{content[:50]}...'")
                                 break
                             else:
                                 logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Ignored peer {speaker} (Randomness check).")
        
        # Heuristic B: High Tension/Paranoia?
        if not should_think and (self.heartbeat.global_tension > 50 or stats.paranoia > 80):
             if random.random() < 0.4: # 40% chance to react to tension
                 should_think = True
                 decision_trigger = ("TENSION", "High Tension")
                 logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Triggered by High Tension ({self.heartbeat.global_tension}%) or Paranoia.")

        # Heuristic C: Random Impulsiveness
        if not should_think and random.random() < 0.05: # 5% random thought
             should_think = True
             decision_trigger = ("RANDOM", "Impulse")

        if not should_think:
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": self.agent.agent_name,
                "status": "IDLE",
                "details": "Standing by."
            })
            # logger.debug(f"{self.agent.soul.name} [OODA: DECIDE] -> No trigger. Idling.")
            return

        # 4. DECIDE (LLM)
        
        # FIX PERF-02: Move Memory Recall BEFORE Lock Acquisition
        # We perform the heavy vector search here, while we are still "thinking" and not holding the floor.
        memory_context_str = ""
        context_str = self._format_context(recent_events[-5:])
        situation = self._extract_situation(recent_events)
        
        if should_think:  # Only recall if we actually intend to speak
            try:
                await self.event_bus.publish(EventType.AGENT_STATUS, {
                    "agent": self.agent.agent_name,
                    "status": "RECALLING",
                    "phase": "D",
                    "details": "Searching memories..."
                })
                memory_query = situation[:200]
                memories = await asyncio.to_thread(
                    self.agent.recall_memories, memory_query
                )
                if memories:
                    memory_str = "\n".join(f"- {m}" for m in memories)
                    memory_context_str = f"Your memories:\n{memory_str}\n\n"
                    logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Recalled {len(memories)} memories.")
                else:
                    logger.debug(f"{self.agent.soul.name} [OODA: DECIDE] -> No memories found.")
            except Exception as mem_err:
                logger.warning(f"Memory recall failed for {self.agent.soul.name}: {mem_err}")

        # Attempt to acquire lock logic

        if not self.heartbeat.conch.owner:
            await self.event_bus.publish(EventType.AGENT_STATUS, {
                "agent": self.agent.agent_name,
                "status": "WAITING_FOR_LOCK",
                "phase": "A",
                "details": "Attempting to claim the floor..."
            })

            acquired = await self.heartbeat.conch.async_acquire(self.agent.agent_name)
            if acquired:
                try:
                    # 5. ACT
                    # Fix #3: Build readable context and extract chairman message as situation
                    # FIX PERF-02: Use pre-calculated memory context
                    full_context_str = f"{memory_context_str}Recent events:\n{context_str}"
                    
                    # (Memory recall removed from here)
                    # (Memory recall removed from here)
                    
                    await self.event_bus.publish(EventType.AGENT_STATUS, {
                        "agent": self.agent.agent_name,
                        "status": "THINKING",
                        "phase": "A",
                        "details": "Formulating response..."
                    })

                    response_data = await asyncio.to_thread(
                        self.agent.speak, situation, full_context_str
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
                    
                    # Fix #1: Mark event as processed ONLY after successful action
                    if decision_trigger:
                        dtype, dcontent = decision_trigger
                        if dtype == "WORLD":
                            self._last_processed_world_event = dcontent
                        elif dtype == "AGENT":
                            self._last_processed_agent_event = dcontent
                    
                    # Deduct Energy
                    self.agent.soul.update_stat("energy", -10)
                    self.agent.save_state()  # Fix #7: persist state after OODA changes
                    self.heartbeat.register_activity()
                    
                finally:
                    await self.heartbeat.conch.async_release(self.agent.agent_name)

    def unsubscribe_all(self):
        """FIX MAJ-08: Remove all EventBus subscriptions for this loop.
        Called before destroying loop instances to prevent duplicate callbacks."""
        self.event_bus.unsubscribe(EventType.WORLD_EVENT, self._sub_world)
        self.event_bus.unsubscribe(EventType.AGENT_SPEAK, self._sub_speak)
        self.event_bus.unsubscribe(EventType.SILENCE_WARNING, self._sub_silence)
        self.event_bus.unsubscribe(EventType.AGENT_STATUS, self._sub_status)
        self.event_bus.unsubscribe(EventType.PHYSICS_COMPLETE, self._sub_physics)
        logger.info(f"[OODA] {self.agent.soul.name} unsubscribed from all events.")
