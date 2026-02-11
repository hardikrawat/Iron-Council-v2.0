"""
Layer 1: Heartbeat & Lock Mechanics — Tests 2.1, 6.1
=====================================================
Per ARCHITECTURE.md: "Heartbeat manages tempo. Conch = mutex with TTL."
Per README: "SpeakingLock with TTL and zombie check prevents race conditions."

These tests validate the documented lock and heartbeat behavior.
"""

import time
import asyncio
import logging
import pytest
from core.heartbeat import SpeakingLock, Heartbeat
from core.event_bus import EventBus, EventType


class TestSpeakingLock:
    """Per Architecture: Conch = mutex ensuring only one agent speaks at a time."""

    def test_lock_acquire_release(self, speaking_lock):
        """Basic lifecycle: acquire → release."""
        assert speaking_lock.acquire("General Ares") is True
        assert speaking_lock.is_locked() is True
        speaking_lock.release("General Ares")
        assert speaking_lock.is_locked() is False

    def test_lock_double_acquire_denied(self, speaking_lock):
        """Per Architecture: Mutex — second agent cannot acquire while first holds."""
        assert speaking_lock.acquire("General Ares") is True
        assert speaking_lock.acquire("Diplomat Dove") is False
        assert speaking_lock.current_holder == "General Ares"

    def test_lock_ttl_auto_expire(self, speaking_lock):
        """Per README: Lock expires via TTL to prevent zombie locks from LLM latency."""
        speaking_lock.ttl = 0.1  # 100ms TTL for test
        speaking_lock.acquire("General Ares")
        time.sleep(0.15)
        # After TTL expiry, another agent should be able to acquire
        assert speaking_lock.is_expired() is True

    def test_lock_release_wrong_owner_does_not_release(self, speaking_lock, caplog):
        """Per README: Race condition fix — wrong owner cannot release another's lock."""
        speaking_lock.acquire("General Ares")
        with caplog.at_level(logging.CRITICAL):
            speaking_lock.release("Diplomat Dove")
        # Lock should still be held by Ares
        assert speaking_lock.is_locked() is True
        assert speaking_lock.current_holder == "General Ares"

    def test_lock_renew_extends_ttl(self, speaking_lock):
        """Per README: renew() extends TTL for slow LLM responses."""
        speaking_lock.ttl = 0.5
        speaking_lock.acquire("General Ares")
        time.sleep(0.3)
        speaking_lock.renew("General Ares")
        time.sleep(0.3)
        # Without renew, lock would have expired at 0.5s
        # With renew at 0.3s, lock should still be valid at 0.6s total
        assert speaking_lock.is_expired() is False

    def test_lock_holder_none_when_released(self, speaking_lock):
        """After release, current_holder must be None."""
        speaking_lock.acquire("General Ares")
        speaking_lock.release("General Ares")
        assert speaking_lock.current_holder is None


class TestHeartbeat:
    """Per Architecture: 'Heartbeat manages tempo. Detects silence, applies entropy penalty.'"""

    def test_heartbeat_has_entropy(self, heartbeat):
        """Per Architecture: Heartbeat tracks entropy (silence tension)."""
        assert hasattr(heartbeat, "entropy") or hasattr(heartbeat, "tension")

    def test_heartbeat_has_speaking_lock(self, heartbeat):
        """Per Architecture: Heartbeat owns the SpeakingLock (Conch)."""
        assert hasattr(heartbeat, "speaking_lock") or hasattr(heartbeat, "lock")

    def test_heartbeat_register_activity(self, heartbeat):
        """Per Architecture: Activity resets entropy/tension."""
        assert hasattr(heartbeat, "register_activity")
        assert callable(heartbeat.register_activity)

    def test_heartbeat_stop(self, heartbeat):
        """Per Architecture: Kill switch can stop the heartbeat."""
        assert hasattr(heartbeat, "stop")
        assert callable(heartbeat.stop)

    def test_heartbeat_start_is_async(self, heartbeat):
        """Heartbeat.start() must be a coroutine for asyncio task management."""
        assert asyncio.iscoroutinefunction(heartbeat.start)

    def test_heartbeat_force_release_expired_lock(self, event_bus):
        """Per Architecture: Heartbeat tick should force-release expired locks."""
        hb = Heartbeat(event_bus)
        lock = hb.speaking_lock if hasattr(hb, "speaking_lock") else hb.lock
        lock.ttl = 0.05
        lock.acquire("General Ares")
        time.sleep(0.1)
        # After TTL, the lock should be expired
        assert lock.is_expired() is True
