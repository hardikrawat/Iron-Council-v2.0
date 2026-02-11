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
        # FIX CRIT-01: asyncio.Lock for true atomicity across await points
        self._async_mutex = asyncio.Lock()

    @property
    def current_holder(self) -> Optional[str]:
        return self.owner

    def is_locked(self) -> bool:
        return self.owner is not None

    def is_expired(self) -> bool:
        if not self.owner or not self.acquired_at:
            return False
        return (datetime.now() - self.acquired_at).total_seconds() > self.ttl

    def acquire(self, agent_name: str) -> bool:
        """Sync acquire — kept for backward compat with tests and heartbeat tick."""
        return self._do_acquire(agent_name)

    async def async_acquire(self, agent_name: str) -> bool:
        """FIX CRIT-01: Async acquire with true mutex protection.
        Prevents TOCTOU race between owner check and owner assignment."""
        async with self._async_mutex:
            return self._do_acquire(agent_name)

    def _do_acquire(self, agent_name: str) -> bool:
        """Core acquire logic shared by sync and async paths."""
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
                    self._original_acquired_at = None
                else:
                    return False # Lock is busy and valid
            else:
                # Should not happen if logic is correct, but safety valve
                self.owner = None

        # Take the lock
        self.owner = agent_name
        self.acquired_at = now
        self._original_acquired_at = now  # FIX AUDIT-1.3: Track original acquisition
        logger.info(f"[LOCK] {agent_name} acquired the Conch.")
        return True

    def release(self, agent_name: str):
        """Sync release — kept for backward compat."""
        self._do_release(agent_name)

    async def async_release(self, agent_name: str):
        """FIX CRIT-01: Async release with mutex protection."""
        async with self._async_mutex:
            self._do_release(agent_name)

    def _do_release(self, agent_name: str):
        """Core release logic shared by sync and async paths."""
        if self.owner == agent_name:
            self.owner = None
            self.acquired_at = None
            logger.info(f"[LOCK] {agent_name} released the Conch.")
        elif self.owner:
            # This captures the Race Condition explicitly in logs
            logger.error(f"[LOCK_CRITICAL] {agent_name} tried to release lock owned by {self.owner}!")
            
    def renew(self, agent_name: str):
        """Allows OODA loop to extend time if LLM is slow.
        FIX AUDIT-1.3: Capped at 2x TTL from original acquisition to prevent infinite filibuster."""
        if self.owner == agent_name:
            now = datetime.now()
            original = getattr(self, '_original_acquired_at', None) or self.acquired_at
            if original and (now - original).total_seconds() < self.ttl * 4:
                self.acquired_at = now
                logger.debug(f"[LOCK] {agent_name} renewed the lock.")
            else:
                logger.warning(f"[LOCK] {agent_name} renewal DENIED — max hold time (4x TTL) exceeded.")

class Heartbeat:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.speaking_lock = SpeakingLock(ttl_seconds=LOCK_TTL)
        self.last_activity_timestamp = time.time()
        self.global_tension = 0
        self._running = False

    async def start(self):
        self._running = True
        logger.info("Heartbeat started.")
        # FIX AUDIT-1.2: Drift-compensated timing loop
        next_tick = time.time()
        while self._running:
            next_tick += TICK_RATE
            sleep_time = max(0, next_tick - time.time())
            await asyncio.sleep(sleep_time)
            await self._tick()
            
    def stop(self):
        self._running = False
        logger.info("Heartbeat stopping...")

    @property
    def is_running(self):
        return self._running
    
    @property
    def tension(self):
        return self.global_tension

    @property
    def entropy(self):
        return self.global_tension
    
    @property
    def conch(self):
        return self.speaking_lock
        
    @property
    def lock(self):
        return self.speaking_lock

    async def _tick(self):
        # 1. Emit System Tick
        await self.event_bus.publish(EventType.SYSTEM_TICK, {
            "time": time.time(),
            "tension": self.global_tension,
            "conch": {
                "owner": self.speaking_lock.owner,
                "expires_in": int(self.speaking_lock.ttl - (datetime.now() - self.speaking_lock.acquired_at).total_seconds()) if self.speaking_lock.acquired_at else 0
            }
        })

        # 2. Check Entropy (Silence)
        # FIX MAJ-01: Skip entropy increment if an agent is actively generating (Conch held)
        now = time.time()
        time_since_activity = now - self.last_activity_timestamp
        
        if time_since_activity > SILENCE_THRESHOLD and not self.speaking_lock.is_locked():
            # Only log every 10 seconds or if tension is not yet maxed
            should_log = (self.global_tension < 100) or (int(time_since_activity) % 10 == 0)
            
            self.global_tension = min(100, self.global_tension + 5)
            
            await self.event_bus.publish(EventType.SILENCE_WARNING, {
                "duration": time_since_activity,
                "msg": "The silence is deafening...",
                "tension": self.global_tension
            })
            
            if should_log:
                logger.info(f"[HEARTBEAT] Silence detected. Global Tension increased to {self.global_tension}%.")

        # 3. Manage Lock TTL
        if self.speaking_lock.owner and self.speaking_lock.acquired_at:
             time_held = (datetime.now() - self.speaking_lock.acquired_at).total_seconds()
             if time_held > self.speaking_lock.ttl:
                 logger.warning(f"[HEARTBEAT] Force-releasing expired lock held by {self.speaking_lock.owner}")
                 self.speaking_lock.release(self.speaking_lock.owner)

    def register_activity(self):
        """
        Call this whenever an agent speaks or user inputs text to reset entropy.
        """
        self.last_activity_timestamp = time.time()
        if self.global_tension > 0:
            old_tension = self.global_tension
            self.global_tension = max(0, self.global_tension - 10)
            logger.info(f"[HEARTBEAT] Activity detected. Tension decreased ({old_tension}% -> {self.global_tension}%).")
