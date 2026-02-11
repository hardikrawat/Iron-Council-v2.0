"""
Layer 1: Event Bus Mechanics — Test 6.1
========================================
Per ARCHITECTURE.md: "Central nervous system. All communication flows through typed events."
Per README: "Decoupled, asynchronous pub/sub system."

These tests validate the EventBus enforces documented pub/sub guarantees.
"""

import asyncio
import pytest
from core.event_bus import EventBus, EventType


class TestEventBusPubSub:
    """Per Architecture: All communication flows through the EventBus."""

    def test_subscribe_and_publish(self, event_bus):
        """Subscribers receive published events."""
        received = []

        async def handler(payload):
            received.append(payload)

        event_bus.subscribe(EventType.WORLD_EVENT, handler)
        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.WORLD_EVENT, {"content": "test message"})
        )
        assert len(received) == 1
        assert received[0]["content"] == "test message"

    def test_publish_no_subscribers_no_error(self, event_bus):
        """Publishing to a channel with no subscribers should not raise."""
        # Should not raise any exception
        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.WORLD_EVENT, {"content": "orphan"})
        )

    def test_multiple_subscribers_all_called(self, event_bus):
        """Per docs: Events broadcast to ALL subscribers (not just one)."""
        received_a = []
        received_b = []

        async def handler_a(payload):
            received_a.append(payload)

        async def handler_b(payload):
            received_b.append(payload)

        event_bus.subscribe(EventType.AGENT_SPEAK, handler_a)
        event_bus.subscribe(EventType.AGENT_SPEAK, handler_b)
        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.AGENT_SPEAK, {"agent": "ares", "content": "hello"})
        )
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_different_event_types_isolated(self, event_bus):
        """Subscribers to one event type don't receive events of another type."""
        received = []

        async def handler(payload):
            received.append(payload)

        event_bus.subscribe(EventType.WORLD_EVENT, handler)
        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.AGENT_SPEAK, {"content": "wrong channel"})
        )
        assert len(received) == 0

    def test_error_in_subscriber_does_not_break_bus(self, event_bus):
        """Per Architecture: Fault isolation — one bad subscriber doesn't crash others."""
        good_received = []

        async def bad_handler(payload):
            raise RuntimeError("Subscriber crash!")

        async def good_handler(payload):
            good_received.append(payload)

        event_bus.subscribe(EventType.WORLD_EVENT, bad_handler)
        event_bus.subscribe(EventType.WORLD_EVENT, good_handler)

        # Should not raise despite bad_handler crashing
        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.WORLD_EVENT, {"content": "test"})
        )
        assert len(good_received) == 1


class TestEventBusThreadSafe:
    """Per Architecture: publish_threadsafe for cross-thread communication."""

    def test_publish_threadsafe_exists(self, event_bus):
        """EventBus must have a publish_threadsafe method for sync→async bridging."""
        assert hasattr(event_bus, "publish_threadsafe")
        assert callable(event_bus.publish_threadsafe)


class TestEventTypesCoverage:
    """Per Architecture: Named event types for system communication."""

    def test_core_event_types_exist(self):
        """Architecture mandates these core event types."""
        required_types = [
            "WORLD_EVENT",      # Chairman messages
            "AGENT_SPEAK",      # Agent responses
            "AGENT_STATUS",     # OODA phase updates
            "SYSTEM_TICK",      # Heartbeat ticks
            "SILENCE_WARNING",  # Entropy alerts
            "MEMORY_ACCESS",    # ChromaDB reads/writes
            "LLM_ACTIVITY",     # LLM calls
        ]
        existing_types = [e.name for e in EventType]
        for rt in required_types:
            assert rt in existing_types, f"EventType.{rt} missing — required by architecture"
