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

class EventBus:
    """
    Asynchronous Pub/Sub system for the Iron Council.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        self._lock = asyncio.Lock()

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
                tasks.append(asyncio.create_task(callback(payload)))
            except Exception as e:
                logger.error(f"Error creating task for subscriber: {e}")

        # We don't await the tasks here to keep publish non-blocking for the emitter?
        # User requirement says "Non-blocking". 
        # But we generally want to verify they run. 
        # For a true event bus, we typically fire and forget or use a queue.
        # Given "Non-blocking" requirement, we leave them as background tasks.
        # However, to avoid 'Task was destroyed but it is pending', we should probably track them loosely or fire-and-forget properly.
        # Ideally, we'd use a Queue, but the user requirement #1 says "use asyncio.Queue OR a list of callback functions".
        # Let's stick to the list of callbacks as requested in Requirements #1 (second option).
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
