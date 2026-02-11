import asyncio
import logging
from enum import Enum
from typing import Dict, List, Callable, Any, Awaitable

logger = logging.getLogger("EventBus")

class EventType(str, Enum):
    WORLD_EVENT = "WORLD_EVENT"   # User or System messages (High Priority)
    AGENT_SPEAK = "AGENT_SPEAK"   # Public text from an agent
    AGENT_THOUGHT = "AGENT_THOUGHT" # Internal monologue (for UI logs)
    SYSTEM_TICK = "SYSTEM_TICK"   # The heartbeat pulse
    LOCK_UPDATE = "LOCK_UPDATE"   # Status of the "Conch"
    SILENCE_WARNING = "SILENCE_WARNING" # Entropy warning
    AGENT_STATUS = "AGENT_STATUS" # Granular activity (Thinking, Idle, etc)
    MEMORY_ACCESS = "MEMORY_ACCESS" # Disk R/W activity
    LLM_ACTIVITY = "LLM_ACTIVITY"   # Neural/LLM processing

class EventBus:
    """
    Asynchronous Pub/Sub system for the Iron Council.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        self._lock = asyncio.Lock()
        self._main_loop: asyncio.AbstractEventLoop = None
        self.background_tasks = set() # Strong references to prevent GC

    def capture_loop(self):
        """Call this from an async context (e.g. FastAPI startup) to capture the main event loop."""
        self._main_loop = asyncio.get_running_loop()
        logger.info("EventBus captured main event loop.")

    def publish_threadsafe(self, event_type: str, payload: Dict[str, Any]):
        """
        Thread-safe publish for use from sync code running in worker threads
        (e.g. agent.speak() called via asyncio.to_thread()).
        """
        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.publish(event_type, payload), self._main_loop)
        else:
            logger.debug(f"Skipped threadsafe publish for {event_type}: no main loop captured.")

    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """
        Registers a callback for a specific event type.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}")

    async def publish(self, event_type: str, payload: Dict[str, Any]):
        """
        Broadcasts an event to all subscribers of that type.
        This is non-blocking (fire and forget from the caller's perspective, 
        but awaits callbacks to ensure order if needed).
        """
        if event_type not in self._subscribers:
            return

        # Create tasks for all subscribers to run concurrently
        callbacks = self._subscribers[event_type]
        tasks = []
        for callback in callbacks:
            try:
                task = asyncio.create_task(callback(payload))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
            except Exception as e:
                logger.error(f"Error creating task for subscriber: {e}")

        # Task reference is now held in self.background_tasks until complete
        pass

    async def publish_sync(self, event_type: str, payload: Dict[str, Any]):
        """
        Awaitable publish if needed for testing or critical sequence.
        """
        if event_type not in self._subscribers:
            return
            
        callbacks = self._subscribers[event_type]
        for callback in callbacks:
            try:
                await callback(payload)
            except Exception as e:
                logger.error(f"Error in subscriber callback for {event_type}: {e}")
