import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


# Handle broken environment (ChromaDB/Pydantic conflict)
import sys
from unittest.mock import MagicMock

try:
    import chromadb
except Exception as e:
    print(f"WARNING: ChromaDB import failed ({e}). Mocking memory system for Visual Layer.")
    sys.modules["chromadb"] = MagicMock()
    sys.modules["chromadb.utils"] = MagicMock()
    sys.modules["chromadb.utils.embedding_functions"] = MagicMock()
    
    # Also mock memory.store if strictly needed, but patching chromadb usually fixes memory.store import
    # If memory.store has other dependencies, we might need more.

# Core Imports explicitly matching main.py structure
from core.agent import IronAgent
from core.llm import LLMService
from core.physics import GamemasterPhysics
from memory.store import SubjectiveMemory
from core.dream import dream_phase, dream_phase_stream, review_agendas


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisualCouncil")

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MECHANIC: INTEGRITY SPY (The Mixin Strategy) ---
class IntegritySpy:
    """
    Wraps the original IntegrityMonitor to capture the 'draft' (hidden thought)
    without modifying the core agent logic.
    """
    def __init__(self, original_integrity):
        self._original = original_integrity
        self.last_draft = None

    def check_integrity(self, soul, draft):
        # Capture the draft before passing it to the real integrity monitor
        self.last_draft = draft
        return self._original.check_integrity(soul, draft)

class VisualIronAgent(IronAgent):
    """
    A wrapper around IronAgent that exposes internal states for the UI.
    Inherits from IronAgent to ensure shared state (reads/writes same JSON).
    """
    def __init__(self, agent_name: str):
        super().__init__(agent_name)
        # Inject the spy
        self.spy = IntegritySpy(self.integrity)
        self.integrity = self.spy  # Replace the instance attribute

    def speak_visual(self, situation_report: str, context: str = "") -> Dict[str, Any]:
        """
        Calls the original speak() method, then extracts the hidden thought
        from the spy. Returns a rich dictionary for the frontend.
        """
        # 1. Generate standard response (modifies state via core logic)
        public_response = self.speak(situation_report, context)

        # 2. Retrieve hidden thought
        hidden_thought = self.spy.last_draft if self.spy.last_draft else public_response

        # 3. Return rich data package
        return {
            "id": self.agent_name,
            "name": self.soul.name,
            "public_text": public_response,
            "hidden_text": hidden_thought,
            "stats": self.soul.dynamic_stats.model_dump(),
            "relationships": self.soul.get_serializable_relationships(),
        }

# --- SIMULATION ENGINE ---
class CouncilSimulation:
    def __init__(self):
        self.llm = LLMService()
        self.physics = GamemasterPhysics(self.llm)
        # No central memory needed here, agents have their own
        
        agent_names = ["general_ares", "diplomat_dove", "banker_midas", "analyst_logic"]
        self.agents = [VisualIronAgent(name) for name in agent_names]
        self.session_log = []
        self.initial_trust_snapshots = {}
        # Capture initial trust baseline
        self.snapshot_trust()


    def snapshot_trust(self):
        """
        Captures current trust scores as baseline for next session.
        """
        self.initial_trust_snapshots = {}
        for agent in self.agents:
            self.initial_trust_snapshots[agent.agent_name] = {
                name: rel.trust_score
                for name, rel in agent.soul.relationships.items()
            }

    def processed_turn(self, user_input: str) -> List[Dict]:
        """
        Runs a full turn of the council (DOMAIN-SEPARATED):
        1. Log User Input
        2. Agents Recall & Speak (Sequential)
        3. Physics: User ↔ Agent (Stats + Goals ONLY)
        4. Reconciliation: Agent ↔ Agent (Relationship Trust ONLY)
        5. Return updates
        """
        self.session_log.append(f"Chairman: {user_input}")
        
        SystemLogger.log_sync("SIMULATION", f"Processing turn for input: {user_input[:20]}...", "INFO")
        
        turn_updates = []
        all_responses = []  # Collected AFTER all speak — for reconciliation

        for agent in self.agents:
            # A. Recall
            SystemLogger.log_sync(agent.agent_name.upper(), "Accessing vector memory...", "DEBUG")
            memories = agent.recall_memories(user_input)
            context_string = ""
            if memories:
                context_string = "I remember: " + " | ".join(memories)
                SystemLogger.log_sync(agent.agent_name.upper(), f"Retrieved {len(memories)} memory fragments.", "INFO")

            # B. Speak (Visual)
            SystemLogger.log_sync(agent.agent_name.upper(), "Generating response...", "DEBUG")
            response_data = agent.speak_visual(user_input, context=context_string)
            
            hidden = response_data['hidden_text']
            if len(hidden) > 40:
                hidden = hidden[:40] + "..."
            SystemLogger.log_sync(agent.agent_name.upper(), f"Draft: {hidden}", "DEBUG")
            self.session_log.append(f"{agent.soul.name}: {response_data['public_text']}")

            # C. Physics — User ↔ Agent ONLY (stats + goals, NO relationships)
            SystemLogger.log_sync("PHYSICS_ENGINE", f"Calculating User↔Agent impact for {agent.soul.name}...", "DEBUG")
            active_goals = [g.description for g in agent.soul.goals if g.active]
            current_stats = agent.soul.dynamic_stats.model_dump()
            impact = self.physics.calculate_impact(
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
                SystemLogger.log_sync("PHYSICS_ENGINE", f"GOAL COMPLETED: {', '.join(completed)}", "CRITICAL")
            
            agent.save_state()
            SystemLogger.log_sync("PHYSICS_ENGINE", "Stats + goals updated.", "INFO")

            response_data['stats'] = agent.soul.dynamic_stats.model_dump()
            response_data['relationships'] = agent.soul.get_serializable_relationships()
            response_data['impact'] = impact
            turn_updates.append(response_data)
            
            # Collect for reconciliation
            all_responses.append({
                "name": agent.soul.name,
                "public_text": response_data['public_text']
            })

        # D. Reconciliation — Agent ↔ Agent ONLY (trust deltas)
        SystemLogger.log_sync("RECONCILIATION", "Analyzing inter-agent dynamics...", "INFO")
        agent_core_values = {
            a.soul.name: a.soul.core_values for a in self.agents
        }
        trust_matrix = self.physics.reconcile_turn(all_responses, agent_core_values)
        
        for agent in self.agents:
            deltas = trust_matrix.get(agent.soul.name, {})
            for target_name, delta in deltas.items():
                if target_name == "vote" or not isinstance(delta, (int, float)):
                    continue  # Phase 2.6: skip vote metadata
                agent.soul.update_relationship(target_name, delta)
            agent.save_state()
        
        SystemLogger.log_sync("RECONCILIATION", f"Trust matrix applied: {trust_matrix}", "INFO")
        SystemLogger.log_sync("SIMULATION", "Turn complete. Awaiting next input.", "INFO")
        return turn_updates

    def generate_dream(self):
        """
        Runs the dream phase and returns the journal entries.
        """
        dream_entries = []
        for agent in self.agents:
            entry = dream_phase(agent, self.session_log)
            dream_entries.append({
                "agent_name": agent.soul.name,
                "entry": entry
            })
        return dream_entries

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Iterate over a copy to handle concurrent modifications
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except RuntimeError:
                # Connection is closed or closing
                try:
                    self.disconnect(connection)
                except ValueError:
                    pass
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                try:
                    self.disconnect(connection)
                except ValueError:
                    pass

manager = ConnectionManager()
simulation = CouncilSimulation()

# Add Persistence Methods to Simulation
def load_history(self):
    try:
        if os.path.exists("db/visual_session.json"):
            with open("db/visual_session.json", "r") as f:
                self.session_log = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load history: {e}")

def save_history(self):
    try:
        os.makedirs("db", exist_ok=True)
        with open("db/visual_session.json", "w") as f:
            json.dump(self.session_log, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

# Monkey patch methods onto simulation instance to avoid full class redefinition if possible, 
# but here we can just update the instance since we have access to it.
simulation.load_history = lambda: load_history(simulation)
simulation.save_history = lambda: save_history(simulation)
simulation.load_history() # Load on startup

@app.websocket("/ws/council")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        initial_state = [
            {
                "id": a.agent_name,
                "name": a.soul.name,
                "stats": a.soul.dynamic_stats.model_dump(),
                "relationships": a.soul.get_serializable_relationships(),
                # NEW: Full Soul Dump for Research Export
                "full_soul": a.soul.model_dump() 
            }
            for a in simulation.agents
        ]
        logger.info(f"Sending initial state for {len(initial_state)} agents to {websocket.client}")
        await websocket.send_json({"type": "init", "data": initial_state})
        
        # NEW: Send Buffered System Logs for Research Export
        if SystemLogger.log_buffer:
            logger.info(f"Sending {len(SystemLogger.log_buffer)} buffered system logs to {websocket.client}")
            for log_msg in SystemLogger.log_buffer:
                await websocket.send_json({
                    "type": "system_log",
                    "content": log_msg,
                    "level": "BUFFERED"
                })

        # Send History
        if simulation.session_log:
             logger.info(f"Sending history ({len(simulation.session_log)} entries) to {websocket.client}")
             await websocket.send_json({"type": "history", "data": simulation.session_log})

        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data[:100]}...")
            message = json.loads(data)
            
            if message.get("type") == "chat":
                user_text = message.get("content")
                logger.info(f"User sent chat message: {user_text[:50]}...")
                
                # Check for end session
                if user_text.lower() in ["end session", "exit", "quit"]:
                    logger.info("Session end requested by user.")
                    await websocket.send_json({"type": "system", "content": "SESSION ENDED. DREAMING..."})
                    await SystemLogger.log("SIMULATION", "Entering dream phase...", "INFO")
                    logger.info("Dream phase initiated.")
                    
                    try:
                        all_dreams = []
                        
                        for agent in simulation.agents:
                            logger.info(f"Dreaming for agent: {agent.soul.name}")
                            await SystemLogger.log(agent.agent_name.upper(), "Commencing deep reflection...", "DEBUG")
                            
                            # Phase 2.6: Calculate trust deltas for dream context
                            snapshot = simulation.initial_trust_snapshots.get(agent.agent_name, {})
                            dream_deltas = {}
                            for name, rel in agent.soul.relationships.items():
                                old_score = snapshot.get(name, 0)
                                dream_deltas[name] = rel.trust_score - old_score
                            logger.info(f"[DREAM_INPUT] {agent.soul.name} trust deltas: {dream_deltas}")
                            
                            stream_id = f"dream_{agent.agent_name}_{int(asyncio.get_event_loop().time())}"
                            await websocket.send_json({
                                "type": "stream_start",
                                "id": stream_id,
                                "agent_id": agent.agent_name,
                                "name": agent.soul.name,
                                "is_dream": True
                            })
                            
                            full_dream_text = ""
                            logger.info(f"Connecting to LLM for {agent.soul.name} dream...")
                            async for chunk in dream_phase_stream(agent, simulation.session_log, trust_deltas=dream_deltas):
                                full_dream_text += chunk
                                await websocket.send_json({
                                    "type": "stream_chunk",
                                    "id": stream_id,
                                    "content": chunk
                                })
                                # Minimal delay for visual effect
                                await asyncio.sleep(0.01)
                            
                            logger.info(f"Dream complete for {agent.soul.name} ({len(full_dream_text)} chars)")
                            await SystemLogger.log(agent.agent_name.upper(), "Reflection finalized.", "INFO")

                            
                            await websocket.send_json({

                                "type": "stream_end",
                                "id": stream_id,
                                "full_data": {
                                    "agent_name": agent.soul.name,
                                    "entry": full_dream_text
                                }
                            })
                            
                            all_dreams.append({
                                "agent_name": agent.soul.name,
                                "entry": full_dream_text
                            })
                            await asyncio.sleep(2.0) # Cool down for local LLM
                            
                        # Post-dream processing: review agendas
                        await SystemLogger.log("SIMULATION", "Reviewing agendas post-dream...", "DEBUG")
                        for agent in simulation.agents:
                            # Calculate trust deltas against INITIAL snapshots (from session start)
                            snapshot = simulation.initial_trust_snapshots.get(agent.agent_name, {})
                            deltas = {}
                            for name, rel in agent.soul.relationships.items():
                                old_score = snapshot.get(name, 0)
                                deltas[name] = rel.trust_score - old_score
                            
                            # Review agendas based on trust deltas
                            await review_agendas(agent, deltas)
                            agent.save_state()
                        
                        await SystemLogger.log("SIMULATION", "All dreams recorded. Agendas reviewed. Session finalized.", "INFO")
                        
                        # Reset trust baseline for next session
                        simulation.snapshot_trust()
                        
                        # We still send the legacy 'dream' type for full state consistency if the UI needs it
                        await websocket.send_json({"type": "dream", "data": all_dreams})
                        
                    except Exception as e:
                        logger.exception("FAILED to stream dreams")
                        await websocket.send_json({"type": "system", "content": f"ERROR IN DREAM PHASE: {str(e)}"})
                    continue


                # Broadcast user message immediately to show it in UI
                user_post = {
                    "type": "user",
                    "content": user_text
                }
                simulation.session_log.append(user_post) # Save to rich log
                simulation.save_history()
                
                await websocket.send_json({
                    "type": "user_post",
                    "content": user_text
                })

                # --- REAL-TIME SEQUENTIAL PROCESSING & STREAMING ---
                # Architecture: Action (Chat) → Consequence (Reconciliation) → Reflection (Dreaming)
                
                await SystemLogger.log("SIMULATION", f"Processing input: {user_text[:30]}...", "INFO")

                all_responses = []  # Collected after ALL agents speak — for reconciliation

                for agent in simulation.agents:
                    # A. Recall
                    await SystemLogger.log(agent.agent_name.upper(), "Accessing neural memory banks...", "DEBUG")
                    memories = await asyncio.to_thread(agent.recall_memories, user_text)
                    context_string = ""
                    if memories:
                        try:
                            memories_str = [str(m) for m in memories]
                            context_string = "I remember: " + " | ".join(memories_str)
                            if any(not isinstance(m, str) for m in memories):
                                await SystemLogger.log(agent.agent_name.upper(), f"WARNING: Memory corruption detected.", "ERROR")
                        except Exception as e:
                             await SystemLogger.log(agent.agent_name.upper(), f"Memory processing error: {e}", "ERROR")
                             context_string = ""

                    # B. Speak (Visual)
                    await SystemLogger.log(agent.agent_name.upper(), "Generating response...", "DEBUG")
                    response_data = await asyncio.to_thread(
                        agent.speak_visual, user_text, context=context_string
                    )
                    
                    hidden = response_data['hidden_text']
                    await SystemLogger.log(agent.agent_name.upper(), f"Draft: {hidden[:50]}...", "DEBUG")

                    # C. Physics — User ↔ Agent ONLY (stats + goals, NO relationships)
                    await SystemLogger.log("PHYSICS_ENGINE", f"Calculating User↔Agent impact for {agent.soul.name}...", "DEBUG")
                    active_goals = [g.description for g in agent.soul.goals if g.active]
                    current_stats = agent.soul.dynamic_stats.model_dump()
                    impact = await asyncio.to_thread(
                        simulation.physics.calculate_impact,
                        agent.agent_name, current_stats, user_text,
                        active_goals
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
                        await SystemLogger.log("PHYSICS_ENGINE", f"GOAL COMPLETED: {', '.join(completed)}", "CRITICAL")
                    
                    agent.save_state()
                    await SystemLogger.log("PHYSICS_ENGINE", "Stats + goals updated.", "INFO")

                    response_data['stats'] = agent.soul.dynamic_stats.model_dump()
                    response_data['relationships'] = agent.soul.get_serializable_relationships()
                    response_data['impact'] = impact

                    # D. SIMULATED STREAMING
                    public_text = response_data['public_text']
                    stream_id = f"{agent.agent_name}_{int(asyncio.get_event_loop().time())}"
                    await manager.broadcast({
                        "type": "stream_start",
                        "id": stream_id,
                        "agent_id": agent.agent_name,
                        "name": agent.soul.name,
                        "stats": response_data['stats'],
                        "relationships": response_data['relationships']
                    })

                    chunk_size = 4
                    for i in range(0, len(public_text), chunk_size):
                        chunk = public_text[i:i+chunk_size]
                        await manager.broadcast({
                            "type": "stream_chunk",
                            "id": stream_id,
                            "content": chunk
                        })
                        await asyncio.sleep(0.02)

                    await manager.broadcast({
                        "type": "stream_end",
                        "id": stream_id, 
                        "full_data": response_data
                    })
                    
                    simulation.session_log.append({
                        "type": "agent_post",
                        "data": response_data
                    })
                    simulation.save_history()
                    
                    # Collect for reconciliation
                    all_responses.append({
                        "name": agent.soul.name,
                        "public_text": response_data['public_text']
                    })

                # E. RECONCILIATION — Agent ↔ Agent ONLY (trust deltas)
                await SystemLogger.log("RECONCILIATION", "Analyzing inter-agent dynamics...", "INFO")
                agent_core_values = {
                    a.soul.name: a.soul.core_values for a in simulation.agents
                }
                trust_matrix = await asyncio.to_thread(
                    simulation.physics.reconcile_turn, all_responses, agent_core_values
                )
                
                for agent in simulation.agents:
                    deltas = trust_matrix.get(agent.soul.name, {})
                    for target_name, delta in deltas.items():
                        if target_name == "vote" or not isinstance(delta, (int, float)):
                            continue  # Phase 2.6: skip vote metadata
                        agent.soul.update_relationship(target_name, delta)
                    agent.save_state()
                
                # Broadcast updated relationships after reconciliation
                # Phase 2.6: Include relationship_type classification
                for agent in simulation.agents:
                    classified_rels = {}
                    for name, rel_data in agent.soul.get_serializable_relationships().items():
                        score = rel_data.get("trust_score", 0)
                        if score >= 20:
                            rel_type = "Allied"
                        elif score <= -20:
                            rel_type = "Hostile"
                        else:
                            rel_type = "Neutral"
                        rel_data["relationship_type"] = rel_type
                        classified_rels[name] = rel_data
                    await manager.broadcast({
                        "type": "relationship_update",
                        "agent_id": agent.agent_name,
                        "relationships": classified_rels
                    })
                
                await SystemLogger.log("RECONCILIATION", f"Trust matrix applied.", "INFO")
                await SystemLogger.log("SIMULATION", "Turn complete. Awaiting next input.", "INFO")
                logger.info("Turn complete.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {websocket.client}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"CRITICAL ERROR in websocket loop for {websocket.client}")
        await SystemLogger.log("SYSTEM", f"CRITICAL WEBSOCKET ERROR: {str(e)}", "ERROR")
        try:
            await websocket.close()
        except:
            pass

# --- SYSTEM LOGGER & KEEPALIVE ---
# Global loop reference for thread-safe logging
main_loop = None

class SystemLogger:
    log_buffer = []  # Store last 1000 logs

    @staticmethod
    async def log(module: str, message: str, level: str = "INFO"):
        """
        Broadcasts a system log to all connected clients and buffers it.
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{module}] > {message}"
        
        # Add basic severity flagging for the frontend
        if level in ["ERROR", "CRITICAL", "MUTINY"]:
            log_entry += " [CRITICAL]"

        # Buffer logic
        SystemLogger.log_buffer.append(log_entry)
        if len(SystemLogger.log_buffer) > 1000:
            SystemLogger.log_buffer.pop(0)

        payload = {
            "type": "system_log",
            "content": log_entry,
            "level": level
        }
        
        if manager:
             await manager.broadcast(payload)

    @staticmethod
    def log_sync(module: str, message: str, level: str = "INFO"):
        """
        Thread-safe wrapper to schedule log on main loop.
        """
        if main_loop and manager:
            asyncio.run_coroutine_threadsafe(
                SystemLogger.log(module, message, level),
                main_loop
            )

async def keepalive_task():
    """
    Sends a heartbeat log every 5 seconds to keep the terminal alive.
    """
    while True:
        await asyncio.sleep(5)
        # Randomize the heartbeat message slightly for flavor
        import random
        heartbeats = [
            "System nominal.",
            "Integrity check passed.",
            "Watching...",
            "Reserving memory block 0x8491...",
            "Ping.",
            "Cycle complete."
        ]
        msg = random.choice(heartbeats)
        await SystemLogger.log("SYSTEM", msg, "DEBUG")

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    asyncio.create_task(keepalive_task())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
