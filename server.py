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
from fastapi.staticfiles import StaticFiles

import warnings

# Silence Pydantic 3.14 compatibility warnings
warnings.filterwarnings(
    "ignore", category=UserWarning, message=".*Pydantic V1 functionality.*"
)

# Setup logging FIRST to avoid NameError if subsequent imports fail
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisualCouncil")

# Silence noisy secondary loggers
logging.getLogger("core.agent").setLevel(
    logging.WARNING
)  # Silence model overrides on import

# Core Imports
from core.agent import IronAgent
from core.llm import LLMService
from core.physics import GamemasterPhysics
from memory.store import SubjectiveMemory
from core.dream import dream_phase, dream_phase_stream, review_agendas

# Phase 3 Imports
from core.event_bus import EventBus, EventType
from core.heartbeat import Heartbeat
from core.ooda import OODALoop, EventBuffer

# Physics System Import moved after logging setup
from core.physics_system import PhysicsSystem

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    global main_loop, active_loops, tui_monitor
    main_loop = asyncio.get_running_loop()
    event_bus.capture_loop()

    # TRUNCATE LOG: Ensure a fresh session for download_log.exe
    # We do this here instead of in the Handler init to avoid uvicorn reload/re-import wipes.
    try:
        if os.path.exists("logs/latest.log"):
            with open("logs/latest.log", "w") as f:
                f.write(f"--- [SESSION_START] {datetime.datetime.now()} ---\n")
                f.flush()
    except Exception as e:
        logger.warning(f"Could not initialize session log: {e}")

    # Initialize Simulation (after logging is ready)
    ensure_simulation()

    # 1. Initialize TUI Monitor (Wait to start until simulation begins)
    tui_monitor = TUIManager(simulation, heartbeat)
    if not (hasattr(app, "cli_mode") and app.cli_mode):
        # If not running through run_cli, we might still want basic logs
        pass

    # 1. Start Support Services
    asyncio.create_task(keepalive_task())

    # Phase 3: Start Heartbeat
    asyncio.create_task(heartbeat.start())

    # Log Frontend Status
    if os.path.exists(FRONTEND_DIST):
        logger.info(f"Serving frontend from {FRONTEND_DIST}")
    else:
        logger.warning(
            "Frontend build directory (ui/dist) not found. Run 'cd ui && npm run build' for production UI."
        )

    # Mark new session in log file
    logger.info(
        "\n"
        + "=" * 50
        + f"\nNEW SESSION STARTED AT {datetime.datetime.now()}\n"
        + "=" * 50
    )

    # Phase 4: Start Physics System
    logger.info("Initializing Physics System...")
    global physics_system
    physics_system = PhysicsSystem(
        event_bus=event_bus,
        physics=simulation.physics,
        agents=simulation.agents,
        transcript=simulation.session_log,  # Shared mutable reference (Physics appends to this)
        on_update=simulation.save_history,  # Save callback
    )
    asyncio.create_task(physics_system.start())

    # Phase 3: Subscribe Bridge
    event_bus.subscribe(EventType.AGENT_SPEAK, bridge_events_to_websocket)
    event_bus.subscribe(EventType.SILENCE_WARNING, bridge_silence_warning)
    event_bus.subscribe(EventType.AGENT_STATUS, bridge_agent_status)
    event_bus.subscribe(EventType.SYSTEM_TICK, bridge_system_tick)

    # Activity Bridge
    from functools import partial

    event_bus.subscribe(
        EventType.MEMORY_ACCESS, partial(bridge_activity_event, event_type="DISK")
    )
    event_bus.subscribe(
        EventType.LLM_ACTIVITY, partial(bridge_activity_event, event_type="LLM")
    )
    event_bus.subscribe(
        EventType.EGO_CHECK, partial(bridge_activity_event, event_type="EGO")
    )
    event_bus.subscribe(
        EventType.PHYSICS_SYNC, partial(bridge_activity_event, event_type="PHYS")
    )
    event_bus.subscribe(
        EventType.STATE_SAVE, partial(bridge_activity_event, event_type="DISK")
    )

    # Phase 3: Initialize OODA Loops
    logger.info("Initializing OODA Loops...")
    for agent in simulation.agents:
        loop = OODALoop(agent, event_bus, heartbeat)
        active_loops.append(loop)
        asyncio.create_task(loop.start())
        logger.info(f"Started OODA loop for {agent.soul.name}")

    yield

    # Shutdown logic (optional but good practice)
    if tui_monitor and tui_monitor.is_active:
        tui_monitor.stop()

    logger.info("Shutting down services...")
    for loop in active_loops:
        loop.stop()
    heartbeat.stop()


app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Serve Frontend (Production Mode) ---
# Mount static files if the build directory exists
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "ui", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )
else:
    # Just a placeholder, we'll log the warning in lifespan
    pass

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
                name: rel.trust_score for name, rel in agent.soul.relationships.items()
            }

    async def generate_dream(self):
        """
        Runs the dream phase and returns the journal entries.
        FIX BUG-09: Properly awaits async dream_phase.
        """
        dream_entries = []
        for agent in self.agents:
            entry = await dream_phase(agent, self.session_log)
            dream_entries.append({"agent_name": agent.soul.name, "entry": entry})
        return dream_entries

    def reset(self):
        """Wipes in-memory session history and re-snapshots trust."""
        self.session_log = []
        self.snapshot_trust()
        logger.info("Simulation in-memory history cleared.")


# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        try:
            await websocket.accept()
            self.active_connections.append(websocket)

            # Send INITIAL_SYNC to new client
            agents_data = []
            for agent in simulation.agents:
                # Prefer cached status for phase/details, but fallback to agent soul for base data
                last_status = agent_status_cache.get(agent.agent_name, {})
                # Include base data
                agents_data.append(
                    {
                        "id": agent.agent_name,
                        "name": agent.soul.name,
                        "status": last_status.get("status", "IDLE"),
                        "phase": last_status.get("phase", ""),
                        "details": last_status.get("details", "Standing by."),
                        "stats": agent.soul.dynamic_stats.model_dump(),
                        "relationships": agent.soul.get_serializable_relationships(),
                        "goals": [g.model_dump() for g in agent.soul.goals],
                    }
                )

            await websocket.send_json(
                {
                    "type": "initial_sync",
                    "data": {
                        "agents": agents_data,
                        "heartbeat": heartbeat.stats if heartbeat else {},
                    },
                }
            )
            logger.info(f"[WS] New client connected. Synced {len(agents_data)} agents.")
        except WebSocketDisconnect:
            logger.warning("[WS] Client disconnected during initial sync.")
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"[WS] Error during initial sync: {e}")
            self.disconnect(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                # FIX CON-01: Use wait_for to prevent hanging on slow clients
                await asyncio.wait_for(connection.send_json(message), timeout=2.0)
            except (RuntimeError, WebSocketDisconnect):
                dead_connections.append(connection)
            except Exception as e:
                # Don't log expected disconnect noise
                if (
                    "broken pipe" not in str(e).lower()
                    and "closed" not in str(e).lower()
                ):
                    logger.debug(f"Error broadcasting to client: {e}")
                dead_connections.append(connection)

        # Batch cleanup
        for dead in dead_connections:
            self.disconnect(dead)


# --- PERSISTENCE ---
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


def ensure_simulation():
    """Lazily initializes the global simulation object if it hasn't been already."""
    global simulation
    if simulation is None:
        simulation = CouncilSimulation(event_bus)
        simulation.start_time = time.time()
        simulation.load_history = lambda: load_history(simulation)
        simulation.save_history = lambda: save_history(simulation)
        simulation.load_history()


manager = ConnectionManager()
simulation: Optional[CouncilSimulation] = None


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
                "timestamp": datetime.datetime.now().isoformat(),
            }

            ws_payload = {"type": "agent_post", "data": agent_data}
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
    ws_payload = {"type": "agent_status_update", "data": payload}
    await manager.broadcast(ws_payload)

    # Special Case: Relationship Update -> Sync Graph
    if payload.get("status") == "RELATIONSHIP_UPDATE":
        agent_name = payload.get("agent")
        agent = next((a for a in simulation.agents if a.agent_name == agent_name), None)

        if agent:
            graph_payload = {
                "type": "relationship_update",
                "agent_id": agent.id,
                "relationships": agent.soul.get_serializable_relationships(),
            }
            await manager.broadcast(graph_payload)
            logger.info(f"[WS_BRIDGE] Synced relationship graph for {agent.soul.name}")

    # Special Case: Stat Update -> Sync Stats
    if payload.get("status") == "STAT_UPDATE":
        stats_payload = {
            "type": "stat_update",
            "agent_id": payload.get("agent"),
            "stats": payload.get("stats"),
            "goals": payload.get("goals"),
        }
        await manager.broadcast(stats_payload)


async def bridge_system_tick(payload: dict):
    """
    Bridges SYSTEM_TICK events to the WebSocket.
    """
    ws_payload = {"type": "system_state_update", "data": payload}
    await manager.broadcast(ws_payload)


async def bridge_activity_event(payload: dict, event_type: str):
    """
    Bridges MEMORY_ACCESS and LLM_ACTIVITY events to the WebSocket.
    Also pipes them into the SystemLogger for the Watchdog terminal.
    """
    ws_payload = {"type": "activity_event", "event": event_type, "data": payload}
    await manager.broadcast(ws_payload)

    # Pipe to Watchdog Terminal
    agent = payload.get("agent", "SYS")

    if event_type == "LLM_ACTIVITY":
        status = payload.get("status", "BUSY")
        if status == "START":
            links = payload.get("active_requests", 1)
            detail = f"NEURAL_LINK_INIT -> {model} [Links: {links}]"
        elif status == "END":
            tps = payload.get("tps", 0)
            tokens = (
                payload.get("total_input_tokens", 0)
                + payload.get("total_output_tokens", 0)
            ) / 1000
            signal = payload.get("signal", "HIGH")
            detail = f"NEURAL_LINK_COMPLETED -> {tps} TPS | {tokens:.1f}k Tokens | Signal: {signal}"
        else:
            detail = payload.get("step") or "EXE"
    else:
        detail = payload.get("step") or payload.get("op") or payload.get("type", "EXE")

    # Standard log call will now be picked up by WebSocketHandler
    logger.info(f"[{event_type}] {agent} -> {detail}")


# --- TUI SYSTEM ---


class TUIManager:
    """
    Manages the professional terminal interface with a fixed header and
    scrolling event feed. Uses ANSI escape codes for cursor management.
    """

    HEADER_SIZE = 14  # Lines reserved for the banner + metrics

    def __init__(self, simulation, heartbeat):
        self.simulation = simulation
        self.heartbeat = heartbeat
        self.is_active = False
        self._lock = asyncio.Lock()

    def start(self):
        """Prepares the terminal for TUI mode."""
        self.is_active = True
        # Enter alternate screen buffer and hide cursor
        print("\033[?1049h\033[?25l", end="")
        # Set scrolling region (from HEADER_SIZE+1 to bottom)
        print(f"\033[{self.HEADER_SIZE + 1};r", end="")
        self.draw_header()
        # Position cursor at the start of scrolling zone
        print(f"\033[{self.HEADER_SIZE + 1};1H", end="", flush=True)

    def stop(self):
        """Restores the terminal to its original state."""
        self.is_active = False
        # Exit alternate screen, reset scrolling region, show cursor
        print("\033[?1049l\033[?25h\033[r", end="", flush=True)

    def draw_header(self):
        """Draws the fixed branding and metrics header."""
        from colorama import Fore, Style

        # Save cursor position
        print("\033[s", end="")
        # Move to top-left
        print("\033[1;1H", end="")

        # 1. Print Banner (Condensed to 7 lines)
        banner = rf"""{Fore.CYAN}{Style.BRIGHT}  _____                      _____                         _ _ 
 |_   _|                    /  __ \                       (_) |
   | |  _ __ ___  _ __      | /  \/ ___  _   _ _ __   ___ _ | |
   | | | '__/ _ \| '_ \     | |    / _ \| | | | '_ \ / __| | | |
  _| |_| | | (_) | | | |    | \__/\ (_) | |_| | | | | (__| | | |
  \___/|_|  \___/|_| |_|     \____/\___/ \__,_|_| |_|\___|_|_|
{Fore.GREEN}  ============================================================={Style.RESET_ALL}"""
        print(banner)

        # 2. Print Credit & Stats
        uptime = (
            int(time.time() - self.simulation.start_time)
            if hasattr(self.simulation, "start_time")
            else 0
        )
        minutes, seconds = divmod(uptime, 60)

        conch_owner = self.heartbeat.conch.owner or "OPEN CHANNEL"
        conch_color = Fore.GREEN if conch_owner == "OPEN CHANNEL" else Fore.YELLOW

        metrics = f"""{Fore.WHITE}  CREATED & CONCEPTUALIZED BY: {Fore.CYAN}{Style.BRIGHT}HARDIK RAWAT{Style.NORMAL}
{Fore.GREEN}  =============================================================
{Fore.WHITE}  STATUS: {Fore.GREEN}ONLINE{Fore.WHITE} | UPTIME: {Fore.YELLOW}{minutes:02d}:{seconds:02d}{Fore.WHITE} | TENSION: {Fore.RED}{int(self.heartbeat.tension)}%{Style.RESET_ALL}
{Fore.WHITE}  CONCH: {conch_color}{conch_owner}{Style.RESET_ALL}
{Fore.GREEN}  =============================================================
"""
        print(metrics, end="")

        # Restore cursor position
        print("\033[u", end="", flush=True)

    def log_event(self, message: str, level: str = "INFO"):
        """Prints a log message into the scrolling region."""
        if not self.is_active:
            print(message)
            return

        from colorama import Fore, Style

        # Map levels to protocol labels and colors
        color = Fore.WHITE
        label = "LOG"

        if "AGENT_SPEAK" in message or "bridge_events" in message:
            color = Fore.CYAN
            label = "ACT"
        elif "PHYSICS" in message or "STAT_UPDATE" in message:
            color = Fore.GREEN
            label = "PROT"
        elif "LLM" in message:
            color = Fore.MAGENTA
            label = "EXE"
        elif level == "ERROR":
            color = Fore.RED
            label = "ERR"
        elif level == "WARNING":
            color = Fore.YELLOW
            label = "WARN"

        # Format: [HH:MM:SS] [LABEL] Content
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = f"{Style.DIM}[{timestamp}]{Style.NORMAL} {Style.BRIGHT}{color}[{label}]{Style.RESET_ALL} "

        # Move cursor to last line to force scrolling within the region if needed
        # We use HEADER_SIZE+1 to ensure we are below the banner
        # Standard logging just prints and the terminal handles the defined scroll region.
        # But we must ensure the cursor isn't in the header area.
        print(f"{prefix}{message}")


tui_monitor: Optional[TUIManager] = None

# --- LOGGING INFRASTRUCTURE ---


class WebSocketLogHandler(logging.Handler):
    """
    Custom logging handler that pipes logs to the SystemLogger buffer
    and broadcasts them to connected WebSocket clients.
    """

    def __init__(self):
        super().__init__()
        self.formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] > %(message)s", datefmt="%H:%M:%S"
        )

    def emit(self, record):
        try:
            msg = self.format(record)

            # Filter out discord/httpx noise if needed, but we want MAXIMAL logging now
            if "GET /" in msg and "200" in msg:
                return  # Filter http access logs to reduce noise

            # Store in buffer
            SystemLogger.log_buffer.append(msg)
            if len(SystemLogger.log_buffer) > 1000:
                SystemLogger.log_buffer.pop(0)

            # Route to TUI if active
            if tui_monitor and tui_monitor.is_active:
                tui_monitor.log_event(record.getMessage(), record.levelname)

            # Broadcast if event loop is running
            if manager:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            manager.broadcast(
                                {
                                    "type": "system_log",
                                    "content": msg,
                                    "level": record.levelname,
                                }
                            )
                        )
                except RuntimeError:
                    pass

        except Exception:
            self.handleError(record)


# Configure Root Logger
# Remove default basicConfig handlers
logging.getLogger().handlers = []

# 1. Terminal Output is handled by TUIManager when active,
# otherwise we use a standard stream handler during startup.
term_handler = logging.StreamHandler()
term_handler.setLevel(logging.INFO)
term_formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s] > %(message)s", datefmt="%H:%M:%S"
)
term_handler.setFormatter(term_formatter)
logging.getLogger().addHandler(term_handler)

# 2. File Handler (The Audit Log)
os.makedirs("logs", exist_ok=True)
# Use append mode to prevent accidental wipes on re-imports/reloads
file_handler = logging.FileHandler("logs/latest.log", mode="a")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s] [%(levelname)s] > %(message)s"
)
file_handler.setFormatter(file_formatter)
logging.getLogger().addHandler(file_handler)

# 3. WebSocket Handler (The Watchdog Bridge)
ws_handler = WebSocketLogHandler()
ws_handler.setLevel(logging.INFO)  # Capture everything INFO and above
logging.getLogger().addHandler(ws_handler)

# Set Root Level
logging.getLogger().setLevel(logging.INFO)

# Set specific loggers to DEBUG if needed for "Maximal" insights
logging.getLogger("uvicorn.access").setLevel(
    logging.WARNING
)  # Keep uvicorn quiet to let our logs shine


# --- SYSTEM LOGGER (Refactored) ---
main_loop = None


class SystemLogger:
    """
    Legacy static accessor for logging, now just a wrapper around standard logging
    to maintain backward compatibility with existing code calls.
    """

    log_buffer = []

    @classmethod
    def clear_buffer(cls):
        logger.info("SystemLogger buffer cleared (Disk & Memory).")
        cls.log_buffer = []

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
        uptime_seconds = int(time.time() - simulation.start_time)

        # System Stats Payload (Minimalistic)
        heartbeat_payload = {
            "type": "heartbeat_pulse",
            "stats": {
                "uptime": uptime_seconds,
                "mem": "64.2MB",  # Static for now to match aesthetic or could be dynamic
                "status": "NORMAL",
                "running": heartbeat._running,  # FIX AUDIT-4.1: Expose running state for UI sync
            },
        }

        if manager:
            await manager.broadcast(heartbeat_payload)

        # Refresh TUI Header
        if tui_monitor and tui_monitor.is_active:
            tui_monitor.draw_header()


async def trigger_dream_phase():
    """
    Fix #2: Full end session + dream phase restoration.
    Pauses OODA loops, streams dream for each agent, reviews agendas, resumes.
    """
    # 1. Broadcast system message to frontend IMMEDIATELY
    await manager.broadcast(
        {"type": "system", "content": "SESSION ENDING. FLUSHING PIPELINE..."}
    )

    # 1.1 Send initial drain status so UI can create progress bar immediately
    await manager.broadcast(
        {
            "type": "drain_status",
            "buffered": [
                loop.agent.agent_name for loop in active_loops if loop._in_cycle
            ],
            "total": len(active_loops),
            "phase": "DRAINING",
        }
    )

    # 2. Pause OODA loops and heartbeat immediately to prevent NEW cycles
    for loop in active_loops:
        loop._running = False
    heartbeat.stop()
    logger.info(
        "OODA loops and heartbeat paused for transition. Waiting for in-flight cycles..."
    )

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
                logger.warning(
                    f"Active drain gate for {loop.agent.soul.name} due to timeout."
                )
            # Update local list isn't thread-safe easily, we'll broadcast a fresh snapshot instead
            return loop.agent.agent_name

        # Run all drains in parallel
        await asyncio.gather(*(drain_agent(l) for l in active_loops))

        # Broadcast FINAL clear status so UI hides banner even if some timed out
        await manager.broadcast(
            {
                "type": "drain_status",
                "buffered": [],
                "total": len(active_loops),
                "phase": "CLEAR",
            }
        )

    logger.info("Pipeline fully drained. Synchronizing final state for Dream Phase...")

    # 5. NOW release conch and notify agents are DREAMING
    # This ensures the "Channel Locked" banner stays up until the agent is actually done speaking.
    if heartbeat.conch.is_locked():
        owner = heartbeat.conch.owner
        heartbeat.conch.release(owner)
        logger.info(
            f"[LOCK] Synchronized release of conch held by {owner} for dream phase."
        )

    # Broadcast clear system state (Open Channel) now that everyone is done
    await manager.broadcast(
        {
            "type": "system_state_update",
            "data": {
                "time": time.time(),
                "tension": heartbeat.tension,
                "conch": {"owner": None, "expires_in": 0},
            },
        }
    )

    # Update agent statuses to DREAMING ONLY AFTER they have finished their OODA cycles
    for agent in simulation.agents:
        await event_bus.publish(
            EventType.AGENT_STATUS,
            {
                "agent": agent.agent_name,
                "status": "DREAMING",
                "phase": "",
                "details": "Writing in Dream Diary...",
            },
        )

    logger.info("Proceeding to dream synthesis.")

    # 5.5 Insert dream session marker into log
    session_timestamp = datetime.datetime.now().isoformat()
    marker = {
        "type": "dream_session_marker",
        "timestamp": session_timestamp,
        "session_id": f"dream-{int(time.time())}",
    }
    simulation.session_log.append(marker)
    await manager.broadcast(marker)

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

    logger.info(
        f"Trust deltas computed: { {a: d for a, d in trust_delta_map.items() if d} }"
    )

    # 7. Stream dream phase for each agent
    for agent in simulation.agents:
        agent_deltas = trust_delta_map.get(agent.agent_name, {})

        # Send stream_start
        await manager.broadcast(
            {
                "type": "stream_start",
                "agent": agent.agent_name,
                "name": agent.soul.name,
                "is_dream": True,
            }
        )

        full_dream = ""
        try:
            async for chunk in dream_phase_stream(
                agent, simulation.session_log, trust_deltas=agent_deltas
            ):
                full_dream += chunk
                await manager.broadcast(
                    {
                        "type": "stream_chunk",
                        "agent": agent.agent_name,
                        "content": chunk,
                    }
                )
        except Exception as e:
            logger.error(f"Error streaming dream for {agent.display_name}: {e}")
            full_dream = f"[Dream failed: {e}]"

        # Send stream_end
        await manager.broadcast(
            {
                "type": "stream_end",
                "agent": agent.agent_name,
                "full_data": {
                    "entry": full_dream,
                    "agent_name": agent.display_name,  # Redundant but helpful for some handlers
                },
            }
        )

        # Persist finalized dream in session log for history
        simulation.session_log.append(
            {
                "type": "dream",
                "timestamp": datetime.datetime.now().isoformat(),
                "data": {"agent_name": agent.display_name, "entry": full_dream},
            }
        )

        # 8. Review agendas for this agent
        try:
            await review_agendas(agent, agent_deltas)
        except Exception as e:
            logger.error(f"Error reviewing agendas for {agent.display_name}: {e}")

        # 9. Save agent state
        agent.save_state()
        logger.info(f"Dream complete for {agent.display_name}")

        # FIX: Broadcast the new "Osmosed" stats to the UI immediately
        await manager.broadcast(
            {
                "type": "stat_update",
                "agent_id": agent.id,
                "stats": agent.soul.dynamic_stats.model_dump(),
                "goals": [g.model_dump() for g in agent.soul.goals],
            }
        )

        await manager.broadcast(
            {
                "type": "relationship_update",
                "agent_id": agent.id,
                "relationships": agent.soul.get_serializable_relationships(),
            }
        )
        logger.info(f"[WS_BRIDGE] Synced post-dream stats for {agent.display_name}")

    # 10. Re-snapshot trust baselines for next session
    simulation.snapshot_trust()

    # 11. Clear session log for next session (preserving dreams for UI history if needed)
    # Actually, the UI history needs to see the dreams.
    # To prevent LLM context bloat, we should probably have a separate 'narrative_history'
    # but for now let's just save it and clear the log.
    simulation.save_history()
    simulation.session_log.clear()  # Clear AFTER saving so they are persisted in JSON

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

    await manager.broadcast(
        {"type": "system", "content": "DREAM PHASE COMPLETE. Council is reconvening."}
    )
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
                "full_soul": a.soul.model_dump(),
            }
            for a in simulation.agents
        ]

        # Send System Config (LLM Provider)
        system_config = {
            "llm_provider": simulation.llm.get_active_model_name(),
            "llm_override": simulation.llm.provider_override,
        }

        await websocket.send_json(
            {"type": "init", "data": initial_state, "config": system_config}
        )

        # Send Logs
        if SystemLogger.log_buffer:
            for log_msg in SystemLogger.log_buffer:
                await websocket.send_json(
                    {"type": "system_log", "content": log_msg, "level": "BUFFERED"}
                )

        # Send History (Always send history even if empty to ensure UI sync)
        safe_log_copy = list(simulation.session_log)
        await websocket.send_json({"type": "history", "data": safe_log_copy})

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "chat":
                user_text = message.get("content")
                logger.info(f"User sent: {user_text}")

                # Fix #1: Echo chairman message immediately to all clients
                await manager.broadcast(
                    {
                        "type": "user_post",
                        "content": user_text,
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                )

                # Check for end session
                if user_text.lower().strip().rstrip(".") in [
                    "end session",
                    "exit",
                    "quit",
                ]:
                    # Fix #2: Full dream phase restoration
                    await trigger_dream_phase()
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
    await manager.broadcast(
        {
            "type": "system_state_update",
            "data": {
                "tension": heartbeat.global_tension,
                "conch": {"owner": None, "expires_in": 0},
            },
        }
    )
    # Log it
    await manager.broadcast(
        {
            "type": "system_log",
            "content": f"[{datetime.datetime.now().isoformat()}] [SYSTEM] > Conch FORCE-RELEASED from {owner} by Chairman.",
        }
    )
    return {"status": f"Conch released from {owner}"}


def clear_terminal():
    """Clears the terminal screen for a clean UI experience."""
    os.system("cls" if os.name == "nt" else "clear")


def print_banner():
    """Prints the Iron Council branding banner with credit to Hardik Rawat."""
    from colorama import Fore, Style, init

    init(autoreset=True)

    # We use a raw string for the ASCII art to avoid escape sequence warnings
    banner_template = r"""
{Fore.CYAN}{Style.BRIGHT}  _____                      _____                         _ _ 
 |_   _|                    /  __ \                       (_) |
   | |  _ __ ___  _ __      | /  \/ ___  _   _ _ __   ___ _ | |
   | | | '__/ _ \| '_ \     | |    / _ \| | | | '_ \ / __| | | |
  _| |_| | | (_) | | | |    | \__/\ (_) | |_| | | | | (__| | | |
  \___/|_|  \___/|_| |_|     \____/\___/ \__,_|_| |_|\___|_|_|
                                                               
{Fore.YELLOW}  [ IRON COUNCIL v2.0 ] - Autonomous Multi-Agent Simulation
{Fore.GREEN}  =============================================================
{Fore.WHITE}  CREATED & CONCEPTUALIZED BY: {Fore.CYAN}{Style.BRIGHT}HARDIK RAWAT{Style.NORMAL}
{Fore.GREEN}  =============================================================
"""
    print(banner_template.format(Fore=Fore, Style=Style))


def run_cli():
    """Entry point for the 'iron-council' console command."""
    import uvicorn
    import sys
    import webbrowser
    import time
    from colorama import Fore, Style

    # Check for keywords to run secondary tools directly
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "setup":
            from setup_env import setup_env

            setup_env(force="--force" in sys.argv)
            return
        elif cmd == "reset":
            from reset import reset_agents, wipe_memory

            reset_agents()
            wipe_memory()

            # Clear In-Memory State (even though process usually exits, good for robustness)
            simulation.reset()
            SystemLogger.clear_buffer()
            agent_status_cache.clear()

            # Clear physical latest.log
            if os.path.exists("logs/latest.log"):
                try:
                    open("logs/latest.log", "w").close()  # Truncate it
                except Exception:
                    pass
            return
        elif cmd in ["start", "run"]:
            pass  # Continue to start server
        else:
            print(f"{Fore.RED}Unknown command: {cmd}")
            print(
                f"{Fore.YELLOW}Use 'iron-council' for interactive mode, or 'setup'/'reset' for maintenance."
            )
            return

    # Clear terminal before showing banner for the "Premium" experience
    clear_terminal()
    print_banner()

    # Interactive Mode if no command or 'start'
    if len(sys.argv) <= 1:
        while True:
            # Clear terminal before showing menu (except first run which is already cleared)
            clear_terminal()
            print_banner()

            print(f"{Fore.WHITE}Welcome to the Iron Council Interface.")
            print(f"{Fore.CYAN}Select an action:")
            print(f"{Fore.GREEN}  1. [START]  Launch Simulation Engine & Dashboard")
            print(f"{Fore.YELLOW}  2. [SETUP]  Configure Environment & Keys")
            print(f"{Fore.RED}  3. [RESET]  Wipe Memory & Reset Agent States")
            print(f"{Fore.WHITE}  4. [EXIT]   Close")

            choice = input(f"\n{Fore.CYAN}Council > {Style.RESET_ALL}").strip()

            if choice == "1":
                # UI BUILD STEP
                print(f"\n🛠️  {Fore.YELLOW}Building UI Frontend (npm run build)...")
                import subprocess

                try:
                    ui_dir = os.path.join(os.path.dirname(__file__), "ui")
                    # Run npm run build and wait for it to finish
                    # Using shell=True to handle npm correctly on all platforms if needed, but array is safer
                    result = subprocess.run(
                        ["npm", "run", "build"],
                        cwd=ui_dir,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        print(f"✅ {Fore.GREEN}UI Build Success.")
                    else:
                        print(f"❌ {Fore.RED}UI Build Failed!")
                        print(result.stderr)
                        confirm_start = input(
                            f"{Fore.YELLOW}Start simulation anyway? (y/N): "
                        ).lower()
                        if confirm_start != "y":
                            continue
                except Exception as e:
                    print(f"⚠️ {Fore.RED}Error during UI build: {e}")
                    confirm_start = input(
                        f"{Fore.YELLOW}Start simulation anyway? (y/N): "
                    ).lower()
                    if confirm_start != "y":
                        continue
                break  # Continue to start server
            elif choice == "2" or choice.lower() == "setup":
                from setup_env import setup_env

                setup_env()
                input(f"\n{Fore.GREEN}Setup complete. Press Enter to return to menu...")
                continue
            elif choice == "3" or choice.lower() == "reset":
                confirm = input(
                    f"{Fore.RED}Are you sure you want to wipe all state? (y/N): "
                ).lower()
                if confirm == "y":
                    from reset import reset_agents, wipe_memory

                    reset_agents()
                    wipe_memory(no_confirm=True)

                    # FIX: Clear In-Memory State
                    ensure_simulation()
                    simulation.reset()
                    SystemLogger.clear_buffer()
                    agent_status_cache.clear()

                    # Clear physical latest.log immediately on RESET
                    if os.path.exists("logs/latest.log"):
                        try:
                            with open("logs/latest.log", "w") as f:
                                f.write(
                                    f"--- [SYSTEM_RESET] {datetime.datetime.now()} ---\n"
                                )
                        except Exception:
                            pass

                    input(
                        f"\n{Fore.GREEN}Reset complete (Disk & Memory). Press Enter to return to menu..."
                    )
                continue
            else:
                print("Exiting...")
                return

    # Start Server logic
    print(f"🚀 {Fore.CYAN}Starting Iron Council Simulation Engine...")

    # Auto-open browser
    def open_browser():
        time.sleep(3)  # Wait for server to initialize
        url = "http://localhost:8000"
        # We don't print this in TUI mode to keep it clean,
        # but for non-TUI it's fine.
        if not (tui_monitor and tui_monitor.is_active):
            print(f"🌐 {Fore.GREEN}Opening Dashboard: {url}")
        webbrowser.open(url)

    import threading

    threading.Thread(target=open_browser, daemon=True).start()

    # Inform app that we are in CLI/TUI mode
    app.cli_mode = True

    # Start TUI Monitor
    if tui_monitor:
        tui_monitor.start()

    try:
        # Run Uvicorn
        # We keep reload=False for TUI stability
        uvicorn.run(
            "server:app", host="0.0.0.0", port=8000, reload=False, log_level="warning"
        )
    finally:
        if tui_monitor and tui_monitor.is_active:
            tui_monitor.stop()


# --- LOGGING ENDPOINTS ---
@app.get("/logs/download")
async def download_logs():
    log_path = "logs/latest.log"
    # Resolve symlink if possible
    real_path = log_path
    if os.path.exists(log_path):
        real_path = os.path.realpath(log_path)

    if os.path.exists(real_path):
        filename = (
            f"IC_SESSION_LOG_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )

        def iterfile():
            with open(real_path, mode="rb") as file_like:
                yield from file_like

        return StreamingResponse(
            iterfile(),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        # Fallback
        try:
            list_of_files = glob.glob("logs/*.log")
            if list_of_files:
                latest_file = max(list_of_files, key=os.path.getctime)
                filename = os.path.basename(latest_file)

                def iterfile_latest():
                    with open(latest_file, mode="rb") as file_like:
                        yield from file_like

                return StreamingResponse(
                    iterfile_latest(),
                    media_type="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={filename}"},
                )
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
            list_of_files = glob.glob("logs/*.log")
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


# --- SPA CATCH-ALL (Must be last) ---
if os.path.exists(FRONTEND_DIST):

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Fallback for React Router (e.g. /dashboard, /settings)
        # API routes are already handled above.
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
