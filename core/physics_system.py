
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
        self.message_buffer = [] # Gamemaster Loop Buffer
        self.pending_tasks = set() # FIX: Track in-flight reactions for clean flush

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
            task = asyncio.create_task(self._process_world_event_for_agent(agent, content))
            self.pending_tasks.add(task)
            task.add_done_callback(self.pending_tasks.discard)
            tasks.append(task)
        
        await asyncio.gather(*tasks)

        # --- PROCESS GAMEMASTER LOOP (Narrative Adjudication) ---
        # Include Chairman input in the buffer
        self.message_buffer.append({"agent": "Chairman", "text": content})
        
        # Trigger every 3 messages (Lowered for responsiveness)
        if len(self.message_buffer) >= 3:
            await self._run_gamemaster_loop()

    async def _process_world_event_for_agent(self, agent: IronAgent, content: str):
        import time
        start_time = time.time()
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
            
            # Save to Subjective Memory (Real-time recall)
            try:
                # We categorize this as an observation so agents can recall it later in the same session
                agent.memory.save_memory(
                    agent_name=agent.agent_name,
                    text=f"Chairman: {content}",
                    emotion="observation"
                )
                logger.debug(f"[MEMORY] Saved World Event to {agent.soul.name}'s memory.")
            except Exception as mem_err:
                logger.error(f"[MEMORY] Failed to save World Event for {agent.soul.name}: {mem_err}")

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
            
            elapsed = time.time() - start_time
            logger.info(f"[PHYSICS] Updated {agent.soul.name} stats via World Event. (Latency: {elapsed:.2f}s)")
            
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

        # FIX: Save speech to Speaker's own memory (Subjective History)
        speaker_agent = next((a for a in self.agents if a.agent_name == speaker_name), None)
        if speaker_agent:
            try:
                speaker_agent.memory.save_memory(
                    agent_name=speaker_name,
                    text=f"I said: {content}",
                    emotion="speech"
                )
            except Exception as mem_err:
                logger.error(f"[MEMORY] Failed to save self-speech for {speaker_name}: {mem_err}")

        # FIX PERF-03: Parallelized Reaction Processing
        # Previously sequential to save VRAM, but caused massive latency (90s+). 
        # Now uses asyncio.gather to process all reactions concurrently.
        reaction_tasks = []
        for listener in self.agents:
            if listener.agent_name == speaker_name:
                continue # Don't react to self
            
            # Queue reaction task
            reaction_tasks.append(self._process_reaction(listener, speaker_name, content))
        
        # Await all reactions in parallel
        if reaction_tasks:
            # FIX: Also track these in pending_tasks for flush synchronization
            # FIX: Properly wrap gather in a coroutine before create_task
            async def run_reactions():
                await asyncio.gather(*reaction_tasks)
            batch_task = asyncio.create_task(run_reactions())
            self.pending_tasks.add(batch_task)
            batch_task.add_done_callback(self.pending_tasks.discard)
            await batch_task

        # --- PROCESS GAMEMASTER LOOP (Narrative Adjudication) ---
        if speaker_name:
             self.message_buffer.append({"agent": speaker_name, "text": content})
             
             # Trigger every 3 messages (Lowered from 4)
             if len(self.message_buffer) >= 3:
                 await self._run_gamemaster_loop()

    async def flush_all(self):
        """
        Forces the Gamemaster loop to run AND waits for all pending reactions.
        Called during session-end for total synchronization.
        """
        logger.info("[PHYSICS] Initiating full flush...")
        
        # 1. Wait for all reaction/impact tasks currently in flight
        if self.pending_tasks:
            logger.info(f"[PHYSICS] Waiting for {len(self.pending_tasks)} pending reaction tasks...")
            await asyncio.gather(*list(self.pending_tasks), return_exceptions=True)
        
        # 2. Flush the Gamemaster loop buffer
        await self.flush_gamemaster_loop()
        
        logger.info("[PHYSICS] Full flush complete.")

    async def flush_gamemaster_loop(self):
        """
        Forces the Gamemaster loop to run on whatever is currently in the buffer.
        Called during session-end or dream-phase transitions.
        """
        if self.message_buffer:
            logger.info("[GAMEMASTER] Flushing buffer for adjudication...")
            await self._run_gamemaster_loop()
        else:
            logger.info("[GAMEMASTER] Flush called but buffer is empty.")

    async def _process_reaction(self, listener: IronAgent, speaker_name: str, content: str):
        import time
        start_time = time.time()
        try:
            # Broadcast Physics Sync START
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "START", "agent": listener.agent_name, "type": "REACTION", "target": speaker_name})

            # Fix #9: Resolve agent_id -> soul name so relationships use correct key
            speaker_soul_name = self._get_soul_name(speaker_name)
            
            delta = await asyncio.to_thread(
                self.physics.calculate_relationship_update,
                speaker_soul_name, content, listener
            )
            
            # Save to Listener's Memory
            try:
                listener.memory.save_memory(
                    agent_name=listener.agent_name,
                    text=f"{speaker_soul_name} said: {content}",
                    emotion="observation"
                )
            except Exception as mem_err:
                logger.error(f"[MEMORY] Failed to save peer-speech for {listener.soul.name}: {mem_err}")

            listener.save_state()
            
            # Fix #6: Broadcast relationship change to frontend
            elapsed = time.time() - start_time
            if delta != 0:
                await self.event_bus.publish(EventType.AGENT_STATUS, {
                    "agent": listener.agent_name,
                    "status": "RELATIONSHIP_UPDATE",
                    "details": f"Trust toward {speaker_soul_name}: {delta:+d} (Latency: {elapsed:.2f}s)",
                    "relationship_data": {
                        "listener": listener.soul.name,
                        "speaker": speaker_soul_name,
                        "delta": delta,
                        "new_score": listener.soul.get_relationship_score(speaker_soul_name)
                    }
                })
            else:
                 logger.info(f"[PHYSICS] {listener.soul.name} had no reaction to {speaker_soul_name}. (Latency: {elapsed:.2f}s)")
            
        except Exception as e:
            logger.error(f"Error processing reaction for {listener.soul.name}: {e}")
        finally:
            await self.event_bus.publish(EventType.PHYSICS_SYNC, {"status": "END"})


    async def _run_gamemaster_loop(self):
        logger.info("[GAMEMASTER] Triggered Narrative Adjudication...")
        
        # 1. Collect Active Goals
        active_goals = {}
        for agent in self.agents:
            a_goals = {g.description: g.progress for g in agent.soul.goals if g.active}
            if a_goals:
                active_goals[agent.soul.name] = a_goals
                
        # 2. Call Arbiter
        # Note: We send a snapshot of the buffer
        buffer_snapshot = list(self.message_buffer)
        
        # Run in thread to avoid blocking
        deltas = await asyncio.to_thread(
            self.physics.adjudicate_narrative,
            buffer_snapshot, active_goals
        )
        
        if not deltas:
             logger.info("[GAMEMASTER] No goal updates adjudicated.")
             # Slide window anyway to avoid stuck buffer? 
             # Yes, we should probably slide or clear. 
             # User said: Keep last message.
             self.message_buffer = [self.message_buffer[-1]]
             return

        # 3. Apply Updates with Dampener
        updates_made = False
        
        for agent_soul_name, goal_impacts in deltas.items():
            # Find the agent
            agent = next((a for a in self.agents if a.soul.name == agent_soul_name), None)
            if not agent: continue
            
            for goal_key, impact_data in goal_impacts.items():
                raw_delta = impact_data.get("delta", 0)
                reason = impact_data.get("reason", "Strategic shift")
                
                # Find exact goal to get current progress for dampening
                target_goal = next((g for g in agent.soul.goals if g.active and g.description == goal_key), None)
                if not target_goal: 
                    # Try fuzzy match if exact fails
                     target_goal = next((g for g in agent.soul.goals if g.active and goal_key in g.description), None)
                
                if target_goal:
                    current = target_goal.progress
                    
                    # DAMPENING LOGIC
                    multiplier = 1.0
                    if current >= 80:
                        multiplier = 0.5
                    elif current >= 50:
                        multiplier = 0.8
                    
                    final_delta = int(raw_delta * multiplier)
                    
                    if final_delta != 0:
                        agent.soul.update_goal_progress(target_goal.description, final_delta)
                        updates_made = True
                        logger.info(f"[GAMEMASTER] {agent.soul.name} Goal '{target_goal.description}': {raw_delta} -> {final_delta} | REASON: {reason}")
                        
                        # Store the verdict for the "Protocol Ledger"
                        # We'll broadcast this specifically as a new event type for the ledger
                        await self.event_bus.publish(EventType.AGENT_STATUS, {
                            "agent": agent.agent_name,
                            "status": "NARRATIVE_VERDICT",
                            "details": reason,
                            "delta": final_delta,
                            "goal": target_goal.description,
                            "stats": agent.soul.dynamic_stats.model_dump(),
                            "goals": [g.model_dump() for g in agent.soul.goals]
                        })

        # 4. Save if updates occurred
        if updates_made:
            for agent in self.agents:
                agent.save_state()

        # 5. Slide Window (Keep Last Message)
        if self.message_buffer:
             self.message_buffer = [self.message_buffer[-1]]

    def _get_soul_name(self, agent_id: str) -> str:
        for a in self.agents:
            if a.agent_name == agent_id:
                return a.soul.name
        return agent_id
