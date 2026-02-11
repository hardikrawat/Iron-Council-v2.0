import asyncio
import json
import logging
import os
import datetime
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
from core.ooda import OODALoop
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

# --- SIMULATION ENGINE ---
class CouncilSimulation:
    def __init__(self, event_bus: EventBus):
        self.llm = LLMService()
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

def save_history(self):
    try:
        os.makedirs("db", exist_ok=True)
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
    
    # Use SystemLogger to broadcast to UI
    await SystemLogger.log("HEARTBEAT", log_msg, "WARNING")

async def bridge_agent_status(payload: dict):
    """
    Bridges AGENT_STATUS events to the WebSocket.
    Also intercepts RELATIONSHIP_UPDATE to sync full graph data.
    """
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
                "agent_id": agent.agent_name,
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
    """
    ws_payload = {
        "type": "activity_event",
        "event": event_type,
        "data": payload
    }
    await manager.broadcast(ws_payload)

# --- SYSTEM LOGGER & KEEPALIVE ---
main_loop = None

class SystemLogger:
    log_buffer = [] 

    @staticmethod
    async def log(module: str, message: str, level: str = "INFO"):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Blacklist static heartbeat logs
        blacklist = ["System nominal.", "Integrity check passed.", "Watching...", "Ping.", "Cycle complete."]
        if message in blacklist:
            return

        log_entry = f"[{timestamp}] [{module}] > {message}"
        
        if level in ["ERROR", "CRITICAL", "MUTINY"]:
            log_entry += " [CRITICAL]"

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
        if main_loop and manager:
            asyncio.run_coroutine_threadsafe(
                SystemLogger.log(module, message, level),
                main_loop
            )

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
                "status": "NORMAL"
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
        transcript=simulation.session_log, # Shared transcript
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
    logger.info("=== END SESSION TRIGGERED ===")
    
    # 1. Broadcast system message to frontend
    await manager.broadcast({
        "type": "system",
        "content": "SESSION ENDED. DREAMING..."
    })
    
    # 2. Pause OODA loops and heartbeat
    for loop in active_loops:
        loop._running = False
    heartbeat.stop()
    logger.info("OODA loops and heartbeat paused for dream phase.")
    
    # 3. Compute trust deltas from session start
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
    
    # 4. Stream dream phase for each agent
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
                    "chunk": chunk
                })
        except Exception as e:
            logger.error(f"Error streaming dream for {agent.soul.name}: {e}")
            full_dream = f"[Dream failed: {e}]"
        
        # Send stream_end
        await manager.broadcast({
            "type": "stream_end",
            "agent": agent.agent_name,
            "full_text": full_dream
        })
        
        # Send dream type for sidebar
        await manager.broadcast({
            "type": "dream",
            "data": {
                "agent_name": agent.soul.name,
                "agent_id": agent.agent_name,
                "entry": full_dream
            }
        })
        
        # 5. Review agendas for this agent
        try:
            await review_agendas(agent, agent_deltas)
        except Exception as e:
            logger.error(f"Error reviewing agendas for {agent.soul.name}: {e}")
        
        # 6. Save agent state
        agent.save_state()
        logger.info(f"Dream complete for {agent.soul.name}")
    
    # 7. Re-snapshot trust baselines for next session
    simulation.snapshot_trust()
    
    # 8. Clear session log for next session
    simulation.session_log.clear()
    simulation.save_history()
    
    # 9. Resume OODA loops and heartbeat
    for loop in active_loops:
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
        await websocket.send_json({"type": "init", "data": initial_state})
        
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
             await websocket.send_json({"type": "history", "data": simulation.session_log})

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
                await SystemLogger.log("CHAIRMAN", f"Broadcasted: {user_text}", "INFO")

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
                active_loops = [] # clear just in case
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
             logger.info("Pausing OODA Loops...")
             for loop in active_loops:
                 loop._running = False
             active_loops.clear()
             
             return {"status": "System PAUSED"}
        return {"status": "System ALREADY STOPPED"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
