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
        # FIX BUG-3: Drain mechanism for clean dream phase transitions
        self._in_cycle = False
        self._drain_gate = False # FIX BUG-C: Gate to suppress speech after drain timeout
        self._cycle_complete = asyncio.Event()
        self._cycle_complete.set()  # Initially "not in a cycle"
        
        # FIX PERF-04: State tracking for trigger persistence
        self._current_decision_trigger = None 
        self._cached_context = None # (Full context string)
        self._cached_situation = None

        
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
            if event.get("status") not in ["STAT_UPDATE", "RELATIONSHIP_UPDATE", "NARRATIVE_VERDICT"]:
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
                
                # FIX: Subjective Reality ('I' Shift)
                if agent_id == self.agent.agent_name:
                    lines.append(f'YOU said: "{e.get("content", "")}"')
                else:
                    lines.append(f'{soul_name} said: "{e.get("content", "")}"')
            elif etype == EventType.AGENT_STATUS:
                # Interoception: Internal monologue about state changes
                status = e.get("status")
                details = e.get("details", "")
                
                if status == "NARRATIVE_VERDICT":
                    delta = e.get("delta", 0)
                    goal = e.get("goal", "objective")
                    trend = "ADVANCED" if delta > 0 else "REGRESSED" if delta < 0 else "STAGNATED"
                    lines.append(f'[INTERNAL SENSE]: Your progress on "{goal}" has {trend} ({delta}%). GM VERDICT: {details}')
                else:
                    lines.append(f'[INTERNAL SENSE]: {details}')
        
        # Fix #2: Synthesize Atmosphere from Global Tension
        if self.heartbeat.global_tension > 20:
             lines.append(f'[Atmosphere: The council is silent. Tension is at {self.heartbeat.global_tension}%.]')
             
        return "\n".join(lines) if lines else "No recent activity."

    def _extract_situation(self, events: List[Dict]) -> str:
        """
        Fix #3: Extract the focus of the current turn.
        STICKY SITUATION: Prioritizes unprocessed WORLD_EVENTs over peer speech.
        """
        # 1. Check for unprocessed WORLD_EVENTs (Sticky)
        for e in reversed(events):
            if e.get("type") == EventType.WORLD_EVENT:
                content = e.get("content", "")
                if content != self._last_processed_world_event:
                    return f'The Chairman addressed the council: "{content}"'
        
        # 2. Fallback to most recent Agent Speech
        for e in reversed(events):
            if e.get("type") == EventType.AGENT_SPEAK:
                speaker = e.get("agent", "Unknown")
                if speaker != self.agent.agent_name:
                    return f'{speaker} just said: "{e.get("content", "")}"'
        
        return "The floor is open. Speak if you have something to contribute."

    async def start(self):
        self._running = True
        while self._running:
            try:
                self._in_cycle = True
                self._cycle_complete.clear()
                await self._run_cycle()
                self._in_cycle = False
                self._cycle_complete.set()
                # Success - reset errors
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                logger.info(f"{self.agent.soul.name} OODA loop cancelled.")
                self._in_cycle = False
                self._cycle_complete.set()
                break
            except Exception as e:
                self._in_cycle = False
                self._cycle_complete.set()
                self._consecutive_errors += 1
                logger.error(f"Error in {self.agent.soul.name} OODA loop (Attempt {self._consecutive_errors}): {e}")
                
                # Report error to UI and clear phase
                await self.event_bus.publish(EventType.AGENT_STATUS, {
                    "agent": self.agent.agent_name,
                    "status": "IDLE",
                    "phase": "",
                    "details": f"Error: {str(e)[:50]}"
                })
                
                # Backoff Strategy
                if self._consecutive_errors > 5:
                    logger.critical(f"{self.agent.soul.name} is COMATOSE due to repeated errors. Sleeping for 60s.")
                    await asyncio.sleep(60)
                    self._consecutive_errors = 0 # Try to wake up eventually
                else:
                    await asyncio.sleep(2 ** self._consecutive_errors) # 2, 4, 8, 16, 32s
            
            # Randomized sleep to desynchronize agents
            await asyncio.sleep(random.uniform(2.0, 4.0))

    def _reset_cycle_state(self):
        """Clears persistent state after successful action or on major reset."""
        self._current_decision_trigger = None
        self._cached_context = None
        self._cached_situation = None
        self._waiting_for_physics = False

    async def wait_for_drain(self, timeout: float = 15.0):
        """FIX BUG-3: Wait for the current in-flight cycle to complete.
        Called by server before dream phase to ensure clean transition."""
        if not self._in_cycle:
            return True
        try:
            await asyncio.wait_for(self._cycle_complete.wait(), timeout=timeout)
            logger.info(f"{self.agent.soul.name} OODA cycle drained successfully.")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"{self.agent.soul.name} drain timed out after {timeout}s. Proceeding anyway.")
            return False

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
             if time.time() - self._physics_wait_start > 120.0:
                 self._waiting_for_physics = False
                 logger.warning(f"{self.agent.soul.name} timed out waiting for physics (120s). Proceeding anyway.")
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
                "phase": "",
                "details": "Standing by."
            })
            # logger.debug(f"{self.agent.soul.name} [OODA: DECIDE] -> No trigger. Idling.")
            return

        # 4. DECIDE (LLM)
        
        # FIX PERF-02/04: Move Memory Recall BEFORE Lock Acquisition & Cache results
        # We only perform heavy search/formatting if this is a NEW trigger or if situation changed.
        # FIX BUG: Ensure we only reuse cache if the TRIGGER is identical
        if self._current_decision_trigger == decision_trigger and self._cached_context:
             full_context_str = self._cached_context
             situation = self._cached_situation
             logger.info(f"{self.agent.soul.name} [OODA: DECIDE] -> Reusing cached context for ongoing trigger.")
        else:
            memory_context_str = ""
            context_str = self._format_context(recent_events[-5:])
            situation = self._extract_situation(recent_events)
            
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

            full_context_str = f"{memory_context_str}Recent events:\n{context_str}"
            
            # Cache for retries
            self._current_decision_trigger = decision_trigger
            self._cached_context = full_context_str
            self._cached_situation = situation

        # Attempt to acquire lock logic

        # Always broadcast intention to acquire before blocking
        # This ensures the UI reflects that the agent is active even if another peer holds the conch.
        await self.event_bus.publish_sync(EventType.AGENT_STATUS, {
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
                # FIX PERF-02/04: Use pre-calculated/cached context
                
                # FIX BUG-B: Use publish_sync to ensure status update completes before blocking call
                await self.event_bus.publish_sync(EventType.AGENT_STATUS, {
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

                # FIX BUG-C: Check drain gate. If True, we timed out and should NOT broadcast.
                if self._drain_gate:
                    logger.warning(f"Drain gate active for {self.agent.soul.name}. Suppressing AGENT_SPEAK broadcast.")
                else:
                    # Publish with hidden text
                    # 1. Update internals (Energy/State) before broadcast so UI gets fresh data
                    self.agent.soul.update_stat("energy", -10)
                    self.agent.save_state()  # Fix #7: persist state after OODA changes

                    # 2. Update Status to ACTING (Sync) with fresh stats
                    await self.event_bus.publish_sync(EventType.AGENT_STATUS, {
                        "agent": self.agent.agent_name,
                        "status": "ACTING",
                        "phase": "A",
                        "details": "Speaking via WebSocket bridge.",
                        "stats": self.agent.soul.dynamic_stats.model_dump(),
                        "goals": [g.model_dump() for g in self.agent.soul.goals]
                    })

                    # 3. Broadcast Speech (Async) - Unblocks the loop from Physics lag
                    await self.event_bus.publish(EventType.AGENT_SPEAK, {
                        "agent": self.agent.agent_name,
                        "content": public_text,
                        "hidden_text": hidden_text
                    })
                
                # Fix #1: Mark event as processed ONLY after successful action
                if decision_trigger:
                    dtype, dcontent = decision_trigger
                    if dtype == "WORLD":
                        self._last_processed_world_event = dcontent
                    elif dtype == "AGENT":
                        self._last_processed_agent_event = dcontent
                
                # Clear persistent state after successful completion
                self._reset_cycle_state()
                
                self.heartbeat.register_activity()
                
            finally:
                # FIX BUG-D: Only release if we still own it (Heartbeat might have force-released)
                if self.heartbeat.conch.owner == self.agent.agent_name:
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
