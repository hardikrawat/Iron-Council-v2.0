"""
Layer 3: Event Throughput — Test 6.1
======================================
Per ARCHITECTURE.md: "All communication flows through typed events."
Per README: "Event Bus is the central nervous system. All components are decoupled."

Tests validate EventBus handles concurrent events, cross-type broadcasting,
and maintains delivery guarantees under load.
"""

import asyncio
import pytest
from core.event_bus import EventBus, EventType


class TestEventThroughput:
    """Per Architecture: EventBus must handle multiple rapid events without dropping."""

    def test_rapid_fire_events_all_delivered(self, event_bus):
        """EventBus should deliver all events even when published rapidly."""
        received = []

        async def handler(payload):
            received.append(payload)

        event_bus.subscribe(EventType.WORLD_EVENT, handler)

        async def rapid_publish():
            for i in range(50):
                await event_bus.publish(EventType.WORLD_EVENT, {"seq": i})

        asyncio.get_event_loop().run_until_complete(rapid_publish())
        assert len(received) == 50, f"Expected 50 events, got {len(received)} — EventBus dropping events"

    def test_multi_type_concurrent_events(self, event_bus):
        """EventBus should handle different event types concurrently."""
        world_events = []
        speak_events = []
        tick_events = []

        async def world_handler(p):
            world_events.append(p)

        async def speak_handler(p):
            speak_events.append(p)

        async def tick_handler(p):
            tick_events.append(p)

        event_bus.subscribe(EventType.WORLD_EVENT, world_handler)
        event_bus.subscribe(EventType.AGENT_SPEAK, speak_handler)
        event_bus.subscribe(EventType.SYSTEM_TICK, tick_handler)

        async def mixed_publish():
            for i in range(10):
                await event_bus.publish(EventType.WORLD_EVENT, {"i": i})
                await event_bus.publish(EventType.AGENT_SPEAK, {"i": i})
                await event_bus.publish(EventType.SYSTEM_TICK, {"i": i})

        asyncio.get_event_loop().run_until_complete(mixed_publish())
        assert len(world_events) == 10
        assert len(speak_events) == 10
        assert len(tick_events) == 10


class TestCrossComponentEventFlow:
    """
    Per Architecture: Events flow across components:
    Chairman → WORLD_EVENT → OODA → AGENT_SPEAK → Physics → AGENT_STATUS → UI
    """

    def test_chained_event_flow(self, event_bus):
        """
        Simulate a chain: WORLD_EVENT triggers a handler that publishes AGENT_SPEAK.
        AGENT_SPEAK triggers a handler that publishes AGENT_STATUS.
        All three events should be received.
        """
        chain_log = []

        async def world_handler(payload):
            chain_log.append("WORLD")
            await event_bus.publish(EventType.AGENT_SPEAK, {
                "agent": "general_ares",
                "content": "Response to world event"
            })

        async def speak_handler(payload):
            chain_log.append("SPEAK")
            await event_bus.publish(EventType.AGENT_STATUS, {
                "agent": "general_ares",
                "status": "STAT_UPDATE"
            })

        async def status_handler(payload):
            chain_log.append("STATUS")

        event_bus.subscribe(EventType.WORLD_EVENT, world_handler)
        event_bus.subscribe(EventType.AGENT_SPEAK, speak_handler)
        event_bus.subscribe(EventType.AGENT_STATUS, status_handler)

        asyncio.get_event_loop().run_until_complete(
            event_bus.publish(EventType.WORLD_EVENT, {"content": "Chairman speaks"})
        )
        assert "WORLD" in chain_log
        assert "SPEAK" in chain_log
        assert "STATUS" in chain_log
