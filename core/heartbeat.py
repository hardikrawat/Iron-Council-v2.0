import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from core.event_bus import EventBus, EventType

logger = logging.getLogger("Heartbeat")

SILENCE_THRESHOLD = 45.0  # Seconds before entropy increases
TICK_RATE = 2.0           # Seconds per heartbeat tick
LOCK_TTL = 60.0           # Seconds before the Conch is forcibly revoked (Increased from 30s)

class SpeakingLock:
    def __init__(self, ttl_seconds=LOCK_TTL):
        self.owner: Optional[str] = None
        self.acquired_at: Optional[datetime] = None
        self.ttl = ttl_seconds
        # No asyncio.Lock needed as operations are atomic in GIL for this purpose

    def acquire(self, agent_name: str) -> bool:
        now = datetime.now()
        
        # Check if current lock is valid
        if self.owner is not None:
            # Auto-expire old locks (The "Zombie Check")
            if self.acquired_at:
                time_held = (now - self.acquired_at).total_seconds()
                if time_held > self.ttl:
                    logger.warning(f"[LOCK] Force-expiring lock held by {self.owner} (TTL {self.ttl}s exceeded)")
                    self.owner = None 
                    self.acquired_at = None
                else:
                    return False # Lock is busy and valid
            else:
                # Should not happen if logic is correct, but safety valve
                self.owner = None

        # Take the lock
        self.owner = agent_name
        self.acquired_at = now
        logger.info(f"[LOCK] {agent_name} acquired the Conch.")
        return True

    def release(self, agent_name: str):
        if self.owner == agent_name:
            self.owner = None
            self.acquired_at = None
            logger.info(f"[LOCK] {agent_name} released the Conch.")
        elif self.owner:
            # This captures the Race Condition explicitly in logs
            logger.error(f"[LOCK_CRITICAL] {agent_name} tried to release lock owned by {self.owner}!")
            
    def renew(self, agent_name: str):
        """Allows OODA loop to extend time if LLM is slow."""
        if self.owner == agent_name:
            self.acquired_at = datetime.now()
            logger.debug(f"[LOCK] {agent_name} renewed the lock.")

class Heartbeat:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.conch = SpeakingLock(ttl_seconds=LOCK_TTL)
        self.last_activity_timestamp = time.time()
        self.global_tension = 0
        self._running = False

    async def start(self):
        self._running = True
        logger.info("Heartbeat started.")
        while self._running:
            await asyncio.sleep(TICK_RATE)
            await self._tick()
            
    def stop(self):
        self._running = False
        logger.info("Heartbeat stopping...")

    @property
    def is_running(self):
        return self._running

    async def _tick(self):
        # 1. Emit System Tick
        await self.event_bus.publish(EventType.SYSTEM_TICK, {
            "time": time.time(),
            "tension": self.global_tension
        })

        # 2. Check Entropy (Silence)
        now = time.time()
        time_since_activity = now - self.last_activity_timestamp
        
        if time_since_activity > SILENCE_THRESHOLD:
            self.global_tension = min(100, self.global_tension + 5)
            await self.event_bus.publish(EventType.SILENCE_WARNING, {
                "duration": time_since_activity,
                "msg": "The silence is deafening...",
                "tension": self.global_tension
            })
            logger.info(f"Silence Warning! Tension: {self.global_tension}")

        # 3. Manage Lock TTL (Passive check via acquire logic mostly, but we can monitor)
        # With new SpeakingLock, acquire() handles force-expiry on next attempt.
        # But we might want to log if it's expired here too.
        if self.conch.owner and self.conch.acquired_at:
             time_held = (datetime.now() - self.conch.acquired_at).total_seconds()
             if time_held > self.conch.ttl:
                 logger.info("Heartbeat detecting expired lock... (will be cleared on next acquire)")
                 # We purely observe here, acquire() does the action.

    def register_activity(self):
        """
        Call this whenever an agent speaks or user inputs text to reset entropy.
        """
        self.last_activity_timestamp = time.time()
        if self.global_tension > 0:
            self.global_tension = max(0, self.global_tension - 10)
            logger.info("Activity detected. Tension decreased.")
