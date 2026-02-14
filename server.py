import asyncio
import json
import logging
import os
import datetime
import time
import glob
from typing import Dict, List, Optional, Any


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
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

# Core Imports explicitly matching main.py structure
from core.agent import IronAgent
from core.llm import LLMService
from core.physics import GamemasterPhysics
from memory.store import SubjectiveMemory
from core.dream import dream_phase, dream_phase_stream, review_agendas

# Phase 3 Imports
from core.event_bus import EventBus, EventType
from core.heartbeat import Heartbeat
from core.ooda import OODALoop, EventBuffer
from core.physics_system import PhysicsSystem

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

# --- GLOBAL EDA STATE ---
event_bus = EventBus()
heartbeat = Heartbeat(event_bus)
active_loops: List[OODALoop] = []
physics_system: Optional[PhysicsSystem] = None

# Latest status for each agent to sync newly connected clients
agent_status_cache: Dict[str, dict] = {}

# --- SIMULATION ENGINE ---
class CouncilSimulation:
    def __init__(self, event_bus: EventBus):
        self.llm = LLMService(event_bus=event_bus)
        self.physics = GamemasterPhysics(self.llm)
        # No central memory needed here, agents have their own
        
        agent_names = ["general_ares", "diplomat_dove", "banker_midas", "analyst_logic"]
        self.agents = [IronAgent(name, event_bus) for name in agent_names]
        self.session_log = []
        self.initial_trust_snapshots = {}
        # Capture initial trust baseline
        self.snapshot_trust()
        self.start_time = datetime.datetime.now()

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



    async def generate_dream(self):
        """
        Runs the dream phase and returns the journal entries.
        FIX BUG-09: Properly awaits async dream_phase.
        """
        dream_entries = []
        for agent in self.agents:
            entry = await dream_phase(agent, self.session_log)
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
        
        # Send INITIAL_SYNC to new client
        agents_data = []
        for agent in simulation.agents:
            # Prefer cached status for phase/details, but fallback to agent soul for base data
            last_status = agent_status_cache.get(agent.agent_name, {})
            # Include base data
            agents_data.append({
                "id": agent.agent_name,
                "name": agent.soul.name,
                "status": last_status.get("status", "IDLE"),
                "phase": last_status.get("phase", ""),
                "details": last_status.get("details", "Standing by."),
                "stats": agent.soul.dynamic_stats.model_dump(),
                "relationships": agent.soul.get_serializable_relationships(),
                "goals": [g.model_dump() for g in agent.soul.goals]
            })
            
        await websocket.send_json({
            "type": "initial_sync",
            "data": {
                "agents": agents_data,
                "heartbeat": heartbeat.stats if heartbeat else {}
            }
        })
        logger.info(f"[WS] New client connected. Synced {len(agents_data)} agents.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except RuntimeError:
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
simulation = CouncilSimulation(event_bus)

# Add Persistence Methods to Simulation
def load_history(self):
    try:
        if os.path.exists("db/visual_session.json"):
            with open("db/visual_session.json", "r") as f:
                self.session_log = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load history: {e}")

# FIX MIN-03: Thread-safe lock for save_history to prevent interleaved writes
import threading
_save_history_lock = threading.Lock()

def save_history(self):
    try:
        os.makedirs("db", exist_ok=True)
        with _save_history_lock:
            with open("db/visual_session.json", "w") as f:
                json.dump(self.session_log, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

simulation.load_history = lambda: load_history(simulation)
simulation.save_history = lambda: save_history(simulation)
simulation.load_history() 

# --- WEB SOCKET BRIDGE (Phase 3) ---
async def bridge_events_to_websocket(payload: dict):
    if "agent" in payload:
        agent_name = payload["agent"]
        content = payload.get("content", "...")
        
        # Find the agent to get full stats
        agent = next((a for a in simulation.agents if a.agent_name == agent_name), None)
        
        if agent:
             hidden_text = payload.get("hidden_text", "")
             
             agent_data = {
                 "id": agent.agent_name,
                 "name": agent.soul.name,
                 "public_text": content,
                 "hidden_text": hidden_text,
                 "stats": agent.soul.dynamic_stats.model_dump(),
                 "relationships": agent.soul.get_serializable_relationships(),
                 "goals": [g.model_dump() for g in agent.soul.goals],
                 "timestamp": datetime.datetime.now().isoformat()
             }
             
             ws_payload = {
                 "type": "agent_post",
                 "data": agent_data
             }
             await manager.broadcast(ws_payload)
             logger.info(f"[WS_BRIDGE] Broadcasted {agent.soul.name} speech.")
             
             # Also log to history - DELEGATED TO PHYSICS SYSTEM
             # simulation.session_log.append(...) 
             # simulation.save_history() 
             # PhysicsSystem listens to AGENT_SPEAK and appends to simulation.session_log and calls save_history.


async def bridge_silence_warning(payload: dict):
    """
    Bridges SILENCE_WARNING events to the frontend System Logger.
    """
    msg = payload.get("msg", "Silence detected.")
    tension = payload.get("tension", 0)
    log_msg = f"{msg} [TENSION: {tension}%]"
    
    # Use standard logger which broadcasts to UI
    if tension > 50:
        logger.warning(f"SILENCE WARNING: {msg} [TENSION: {tension}%]")
    else:
        logger.info(f"Silence detected. Tension at {tension}%.")

async def bridge_agent_status(payload: dict):
    """
    Bridges AGENT_STATUS events to the WebSocket.
    Also intercepts RELATIONSHIP_UPDATE to sync full graph data.
    """
    # Cache status for future INITIAL_SYNC
    agent_name = payload.get("agent")
    if agent_name:
        agent_status_cache[agent_name] = payload

    # Standard status update
    ws_payload = {
        "type": "agent_status_update",
        "data": payload
    }
    await manager.broadcast(ws_payload)

    # Special Case: Relationship Update -> Sync Graph
    if payload.get("status") == "RELATIONSHIP_UPDATE":
        agent_name = payload.get("agent")
        agent = next((a for a in simulation.agents if a.agent_name == agent_name), None)
        
        if agent:
            graph_payload = {
                "type": "relationship_update",
                "agent_id": agent.id,
                "relationships": agent.soul.get_serializable_relationships()
            }
            await manager.broadcast(graph_payload)
            logger.info(f"[WS_BRIDGE] Synced relationship graph for {agent.soul.name}")

    # Special Case: Stat Update -> Sync Stats
    if payload.get("status") == "STAT_UPDATE":
        stats_payload = {
            "type": "stat_update",
            "agent_id": payload.get("agent"),
            "stats": payload.get("stats"),
            "goals": payload.get("goals")
        }
        await manager.broadcast(stats_payload)

async def bridge_system_tick(payload: dict):
    """
    Bridges SYSTEM_TICK events to the WebSocket.
    """
    ws_payload = {
        "type": "system_state_update",
        "data": payload
    }
    await manager.broadcast(ws_payload)

async def bridge_activity_event(payload: dict, event_type: str):
    """
    Bridges MEMORY_ACCESS and LLM_ACTIVITY events to the WebSocket.
    Also pipes them into the SystemLogger for the Watchdog terminal.
    """
    ws_payload = {
        "type": "activity_event",
        "event": event_type,
        "data": payload
    }
    await manager.broadcast(ws_payload)

    # Pipe to Watchdog Terminal
    agent = payload.get("agent", "SYS")
    detail = payload.get("step") or payload.get("op") or payload.get("type", "EXE")
    # Standard log call will now be picked up by WebSocketHandler
    logger.info(f"[{event_type}] {agent} -> {detail}")

# --- LOGGING INFRASTRUCTURE ---

class WebSocketLogHandler(logging.Handler):
    """
    Custom logging handler that pipes logs to the SystemLogger buffer
    and broadcasts them to connected WebSocket clients.
    """
    def __init__(self):
        super().__init__()
        self.formatter = logging.Formatter("[%(asctime)s] [%(name)s] > %(message)s", datefmt="%H:%M:%S")

    def emit(self, record):
        try:
            msg = self.format(record)
            
            # Filter out discord/httpx noise if needed, but we want MAXIMAL logging now
            if "GET /" in msg and "200" in msg: return # Filter http access logs to reduce noise
            
            # Store in buffer
            SystemLogger.log_buffer.append(msg)
            if len(SystemLogger.log_buffer) > 1000:
                SystemLogger.log_buffer.pop(0)

            # Broadcast if event loop is running
            if manager:
                # We need to schedule this on the main loop
                # If we are in the main loop, we can await it? No, emit is sync.
                # We must use create_task/run_coroutine_threadsafe
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                         asyncio.create_task(manager.broadcast({
                             "type": "system_log",
                             "content": msg,
                             "level": record.levelname
                         }))
                except RuntimeError:
                    # Initial setup might happen before loop is running
                    pass

        except Exception:
            self.handleError(record)

# Configure Root Logger
# Remove default basicConfig handlers
logging.getLogger().handlers = []

# 1. Terminal Handler (Formatted)
term_handler = logging.StreamHandler()
term_handler.setLevel(logging.INFO)
term_formatter = logging.Formatter("[%(asctime)s] [%(name)s] > %(message)s", datefmt="%H:%M:%S")
term_handler.setFormatter(term_formatter)
logging.getLogger().addHandler(term_handler)

# 2. WebSocket Handler (The Watchdog Bridge)
ws_handler = WebSocketLogHandler()
ws_handler.setLevel(logging.INFO) # Capture everything INFO and above
logging.getLogger().addHandler(ws_handler)

# Set Root Level
logging.getLogger().setLevel(logging.INFO)

# Set specific loggers to DEBUG if needed for "Maximal" insights
logging.getLogger("uvicorn.access").setLevel(logging.WARNING) # Keep uvicorn quiet to let our logs shine


# --- SYSTEM LOGGER (Refactored) ---
main_loop = None

class SystemLogger:
    """
    Legacy static accessor for logging, now just a wrapper around standard logging
    to maintain backward compatibility with existing code calls.
    """
    log_buffer = [] 

    @staticmethod
    async def log(module: str, message: str, level: str = "INFO"):
        # Map legacy calls to standard logging
        log_instance = logging.getLogger(module)
        if level.upper() == "ERROR":
            log_instance.error(message)
        elif level.upper() == "WARNING":
            log_instance.warning(message)
        elif level.upper() == "CRITICAL":
            log_instance.critical(message)
        else:
            log_instance.info(message)

    @staticmethod
    def log_sync(module: str, message: str, level: str = "INFO"):
        # Just call the standard logger, it handles sync emit
        log_instance = logging.getLogger(module)
        if level.upper() == "ERROR":
            log_instance.error(message)
        else:
             log_instance.info(message)

async def keepalive_task():
    """
    Silent heartbeat that updates system metrics and triggers the 'Pulse' LED
    without cluttering the main log scroll.
    """
    while True:
        await asyncio.sleep(5)
        
        # Calculate Uptime
        uptime_delta = datetime.datetime.now() - simulation.start_time
        uptime_seconds = int(uptime_delta.total_seconds())
        
        # System Stats Payload (Minimalistic)
        heartbeat_payload = {
            "type": "heartbeat_pulse",
            "stats": {
                "uptime": uptime_seconds,
                "mem": "64.2MB", # Static for now to match aesthetic or could be dynamic
                "status": "NORMAL",
                "running": heartbeat._running  # FIX AUDIT-4.1: Expose running state for UI sync
            }
        }
        
        if manager:
            await manager.broadcast(heartbeat_payload)

@app.on_event("startup")
async def startup_event():
    global main_loop, active_loops
    main_loop = asyncio.get_running_loop()
    event_bus.capture_loop()
    
    # 1. Start Support Services
    asyncio.create_task(keepalive_task())
    
    # Phase 3: Start Heartbeat
    asyncio.create_task(heartbeat.start())

    # Phase 4: Start Physics System
    logger.info("Initializing Physics System...")
    global physics_system
    physics_system = PhysicsSystem(
        event_bus=event_bus,
        physics=simulation.physics,
        agents=simulation.agents,
        transcript=simulation.session_log, # Shared mutable reference (Physics appends to this)
        on_update=simulation.save_history  # Save callback
    )
    asyncio.create_task(physics_system.start())

    
    # Phase 3: Subscribe Bridge
    event_bus.subscribe(EventType.AGENT_SPEAK, bridge_events_to_websocket)
    event_bus.subscribe(EventType.SILENCE_WARNING, bridge_silence_warning)
    event_bus.subscribe(EventType.AGENT_STATUS, bridge_agent_status)
    event_bus.subscribe(EventType.SYSTEM_TICK, bridge_system_tick)
    
    # Activity Bridge
    from functools import partial
    event_bus.subscribe(EventType.MEMORY_ACCESS, partial(bridge_activity_event, event_type="DISK"))
    event_bus.subscribe(EventType.LLM_ACTIVITY, partial(bridge_activity_event, event_type="LLM"))
    event_bus.subscribe(EventType.EGO_CHECK, partial(bridge_activity_event, event_type="EGO"))
    event_bus.subscribe(EventType.PHYSICS_SYNC, partial(bridge_activity_event, event_type="PHYS"))
    event_bus.subscribe(EventType.STATE_SAVE, partial(bridge_activity_event, event_type="DISK"))
    
    # Phase 3: Initialize OODA Loops
    logger.info("Initializing OODA Loops...")
    for agent in simulation.agents:
        loop = OODALoop(agent, event_bus, heartbeat)
        active_loops.append(loop)
        asyncio.create_task(loop.start())
        logger.info(f"Started OODA loop for {agent.soul.name}")

async def _handle_end_session():
    """
    Fix #2: Full end session + dream phase restoration.
    Pauses OODA loops, streams dream for each agent, reviews agendas, resumes.
    """
    # 1. Broadcast system message to frontend IMMEDIATELY
    await manager.broadcast({
        "type": "system",
        "content": "SESSION ENDING. FLUSHING PIPELINE..."
    })

    # 1.1 Send initial drain status so UI can create progress bar immediately
    await manager.broadcast({
        "type": "drain_status",
        "buffered": [loop.agent.agent_name for loop in active_loops if loop._in_cycle],
        "total": len(active_loops),
        "phase": "DRAINING"
    })

    # 2. Pause OODA loops and heartbeat immediately to prevent NEW cycles
    for loop in active_loops:
        loop._running = False
    heartbeat.stop()
    logger.info("OODA loops and heartbeat paused for transition. Waiting for in-flight cycles...")

    # 3. Flush the PhysicsSystem buffer (Narrative Adjudication) + Pending Reactions
    # This must happen before we start the dream phase so all events are processed.
    global physics_system
    if physics_system:
        logger.info("Flushing PhysicsSystem pipeline and pending tasks...")
        await physics_system.flush_all()

    # 4. Drain in-flight OODA cycles concurrently BEFORE starting dream phase
    if active_loops:
        logger.info(f"Draining {len(active_loops)} OODA loops concurrently...")
        
        async def drain_agent(loop):
            drained = await loop.wait_for_drain(timeout=30.0)
            if not drained:
                loop._drain_gate = True
                logger.warning(f"Active drain gate for {loop.agent.soul.name} due to timeout.")
            # Update local list isn't thread-safe easily, we'll broadcast a fresh snapshot instead
            return loop.agent.agent_name

        # Run all drains in parallel
        await asyncio.gather(*(drain_agent(l) for l in active_loops))
        
        # Broadcast FINAL clear status so UI hides banner even if some timed out
        await manager.broadcast({
            "type": "drain_status",
            "buffered": [],
            "total": len(active_loops),
            "phase": "CLEAR"
        })
    
    logger.info("Pipeline fully drained. Synchronizing final state for Dream Phase...")

    # 5. NOW release conch and notify agents are DREAMING
    # This ensures the "Channel Locked" banner stays up until the agent is actually done speaking.
    if heartbeat.conch.is_locked():
        owner = heartbeat.conch.owner
        heartbeat.conch.release(owner)
        logger.info(f"[LOCK] Synchronized release of conch held by {owner} for dream phase.")

    # Broadcast clear system state (Open Channel) now that everyone is done
    await manager.broadcast({
        "type": "system_state_update",
        "data": {
            "time": time.time(),
            "tension": heartbeat.tension,
            "conch": {
                "owner": None,
                "expires_in": 0
            }
        }
    })

    # Update agent statuses to DREAMING ONLY AFTER they have finished their OODA cycles
    for agent in simulation.agents:
        await event_bus.publish(EventType.AGENT_STATUS, {
            "agent": agent.agent_name,
            "status": "DREAMING",
            "phase": "",
            "details": "Writing in Dream Diary..."
        })

    logger.info("Proceeding to dream synthesis.")
    
    # 6. Compute trust deltas from session start
    trust_delta_map = {}  # {agent_name: {other_soul_name: delta}}
    for agent in simulation.agents:
        agent_deltas = {}
        initial_snapshot = simulation.initial_trust_snapshots.get(agent.agent_name, {})
        for name, rel in agent.soul.relationships.items():
            old_score = initial_snapshot.get(name, 0)
            delta = rel.trust_score - old_score
            if delta != 0:
                agent_deltas[name] = delta
        trust_delta_map[agent.agent_name] = agent_deltas
    
    logger.info(f"Trust deltas computed: { {a: d for a, d in trust_delta_map.items() if d} }")
    
    # 7. Stream dream phase for each agent
    for agent in simulation.agents:
        agent_deltas = trust_delta_map.get(agent.agent_name, {})
        
        # Send stream_start
        await manager.broadcast({
            "type": "stream_start",
            "agent": agent.agent_name,
            "name": agent.soul.name,
            "is_dream": True
        })
        
        full_dream = ""
        try:
            async for chunk in dream_phase_stream(agent, simulation.session_log, trust_deltas=agent_deltas):
                full_dream += chunk
                await manager.broadcast({
                    "type": "stream_chunk",
                    "agent": agent.agent_name,
                    "content": chunk
                })
        except Exception as e:
            logger.error(f"Error streaming dream for {agent.display_name}: {e}")
            full_dream = f"[Dream failed: {e}]"
        
        # Send stream_end
        await manager.broadcast({
            "type": "stream_end",
            "agent": agent.agent_name,
            "full_data": {
                "entry": full_dream,
                "agent_name": agent.display_name  # Redundant but helpful for some handlers
            }
        })
        
        # 8. Review agendas for this agent
        try:
            await review_agendas(agent, agent_deltas)
        except Exception as e:
            logger.error(f"Error reviewing agendas for {agent.display_name}: {e}")
        
        # 9. Save agent state
        agent.save_state()
        logger.info(f"Dream complete for {agent.display_name}")

        # FIX: Broadcast the new "Osmosed" stats to the UI immediately
        await manager.broadcast({
            "type": "stat_update",
            "agent_id": agent.id,
            "stats": agent.soul.dynamic_stats.model_dump(),
            "goals": [g.model_dump() for g in agent.soul.goals]
        })
        
        await manager.broadcast({
            "type": "relationship_update",
            "agent_id": agent.id,
            "relationships": agent.soul.get_serializable_relationships()
        })
        logger.info(f"[WS_BRIDGE] Synced post-dream stats for {agent.display_name}")
    
    # 10. Re-snapshot trust baselines for next session
    simulation.snapshot_trust()
    
    # 11. Clear session log for next session
    simulation.session_log.clear()
    simulation.save_history()
    
    # 12. Resume OODA loops and heartbeat
    # FIX BUG-01/05: Clear stale event buffers and processed-event trackers
    for loop in active_loops:
        loop.memory = EventBuffer()
        loop._last_processed_world_event = None
        loop._last_processed_agent_event = None
        loop._waiting_for_physics = False
        loop._running = True
        asyncio.create_task(loop.start())
    asyncio.create_task(heartbeat.start())
    
    await manager.broadcast({
        "type": "system",
        "content": "DREAM PHASE COMPLETE. Council is reconvening."
    })
    logger.info("=== DREAM PHASE COMPLETE — OODA loops resumed ===")


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
                "full_soul": a.soul.model_dump() 
            }
            for a in simulation.agents
        ]
        
        # Send System Config (LLM Provider)
        system_config = {
            "llm_provider": simulation.llm.get_active_model_name(),
            "llm_override": simulation.llm.provider_override
        }
        
        await websocket.send_json({
            "type": "init", 
            "data": initial_state,
            "config": system_config
        })
        
        # Send Logs
        if SystemLogger.log_buffer:
            for log_msg in SystemLogger.log_buffer:
                await websocket.send_json({
                    "type": "system_log",
                    "content": log_msg,
                    "level": "BUFFERED"
                })

        # Send History
        if simulation.session_log:
             # Fix #6: Copying list to prevent "dictionary changed size during iteration" (or list mutation race)
             safe_log_copy = list(simulation.session_log)
             await websocket.send_json({"type": "history", "data": safe_log_copy})

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "chat":
                user_text = message.get("content")
                logger.info(f"User sent: {user_text}")
                
                # Fix #1: Echo chairman message immediately to all clients
                await manager.broadcast({
                    "type": "user_post",
                    "content": user_text,
                    "timestamp": datetime.datetime.now().isoformat()
                })
                
                # Check for end session
                if user_text.lower().strip().rstrip('.') in ["end session", "exit", "quit"]:
                    # Fix #2: Full dream phase restoration
                    await _handle_end_session()
                    continue

                # PHASE 3: EVENT DRIVEN
                # Instead of processed_turn, we publish to EventBus
                await event_bus.publish(EventType.WORLD_EVENT, {"content": user_text})
                
                # Notify Heartbeat of activity
                heartbeat.register_activity()
                logger.info(f"[CHAIRMAN] Broadcasted: {user_text}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket Error")
        manager.disconnect(websocket)

# --- KILL SWITCH ---
@app.post("/admin/toggle_heartbeat")
async def toggle_heartbeat(active: bool):
    global active_loops
    if active:
        if not heartbeat.is_running:
            # 1. Start Heartbeat
            asyncio.create_task(heartbeat.start())
            
            # 2. Resume OODA Loops if they were stopped
            if not active_loops:
                logger.info("Resuming OODA Loops...")
                active_loops = []
                for agent in simulation.agents:
                    loop = OODALoop(agent, event_bus, heartbeat)
                    active_loops.append(loop)
                    asyncio.create_task(loop.start())
                    logger.info(f"Restarted OODA loop for {agent.soul.name}")
            
            return {"status": "System RESUMED"}
        return {"status": "System ALREADY RUNNING"}
    else:
        if heartbeat.is_running:
             # 1. Stop Heartbeat
             heartbeat.stop() 
             
             # 2. Stop OODA Loops
             # FIX MAJ-08: Unsubscribe old loops to prevent duplicate callbacks on resume
             logger.info("Pausing OODA Loops...")
             for loop in active_loops:
                 loop._running = False
                 loop.unsubscribe_all()
             active_loops.clear()
             
             return {"status": "System PAUSED"}
        return {"status": "System ALREADY STOPPED"}

# --- FIX 6.3: Dedicated endpoint to force-release the Conch without killing the system ---
@app.post("/admin/force_release_conch")
async def force_release_conch():
    """Force-releases the speaking lock (Conch) without halting the heartbeat or OODA loops.
    FIX BUG-02: Uses async mutex to prevent racing with OODA lock operations."""
    async with heartbeat.conch._async_mutex:
        owner = heartbeat.conch.owner
        if owner:
            logger.warning(f"[ADMIN] Force-releasing Conch from {owner}")
            heartbeat.conch.owner = None
            heartbeat.conch.acquired_at = None
            heartbeat.conch._original_acquired_at = None
        else:
            return {"status": "Conch is not held"}
    
    # Broadcast updated system state so UI reflects immediately
    await manager.broadcast({
        "type": "system_state_update",
        "data": {
            "tension": heartbeat.global_tension,
            "conch": {"owner": None, "expires_in": 0}
        }
    })
    # Log it
    await manager.broadcast({
        "type": "system_log",
        "content": f"[{datetime.datetime.now().isoformat()}] [SYSTEM] > Conch FORCE-RELEASED from {owner} by Chairman."
    })
    return {"status": f"Conch released from {owner}"}

# --- LOGGING ENDPOINTS ---
@app.get("/logs/download")
async def download_logs():
    log_path = "logs/latest.log"
    # Resolve symlink if possible
    real_path = log_path
    if os.path.exists(log_path):
        real_path = os.path.realpath(log_path)
    
    if os.path.exists(real_path):
        filename = f"IC_SESSION_LOG_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        def iterfile():
            with open(real_path, mode="rb") as file_like:
                yield from file_like

        return StreamingResponse(iterfile(), media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={filename}"})
    else:
        # Fallback
        try:
            list_of_files = glob.glob('logs/*.log') 
            if list_of_files:
                latest_file = max(list_of_files, key=os.path.getctime)
                filename = os.path.basename(latest_file)
                
                def iterfile_latest():
                    with open(latest_file, mode="rb") as file_like:
                        yield from file_like
                        
                return StreamingResponse(iterfile_latest(), media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={filename}"})
        except Exception as e:
            logger.error(f"Error finding log file: {e}")
            pass
    
    raise HTTPException(status_code=404, detail="Log file not found")

@app.get("/logs/size")
async def get_log_size():
    log_path = "logs/latest.log"
    size_bytes = 0
    
    real_path = log_path
    if os.path.exists(log_path):
        real_path = os.path.realpath(log_path)

    if os.path.exists(real_path):
        size_bytes = os.path.getsize(real_path)
    else:
        # Try finding latest
        try:
            list_of_files = glob.glob('logs/*.log')
            if list_of_files:
                 latest_file = max(list_of_files, key=os.path.getctime)
                 size_bytes = os.path.getsize(latest_file)
        except Exception:
            pass
            
    # Format size
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        
    return {"size_bytes": size_bytes, "size_formatted": size_str}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
