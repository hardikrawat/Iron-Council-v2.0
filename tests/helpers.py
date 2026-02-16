"""
Iron Council v2.0 — Test Helpers
==================================
Utility functions used across all test layers.
"""

import asyncio
from contextlib import contextmanager
from typing import List
from core.event_bus import EventBus, EventType
from core.schema import AgentSoul, DynamicStats, RelationshipModel, Goal


class SoulFactory:
    """Quick-build AgentSoul objects for specific test archetypes."""

    @staticmethod
    def ares(confidence=75, paranoia=15, loyalty=20, stress=25, energy=100, **kwargs):
        return AgentSoul(
            name="General Ares",
            archetype="General",
            base_model="qwen2.5:7b",
            core_values=["Strength", "Hierarchy", "Decisiveness"],
            dynamic_stats=DynamicStats(
                confidence=confidence,
                paranoia=paranoia,
                loyalty_to_chairman=loyalty,
                stress_level=stress,
                energy=energy,
            ),
            relationships=kwargs.get(
                "relationships",
                {
                    "Diplomat Dove": RelationshipModel(trust_score=-50),
                    "Banker Midas": RelationshipModel(trust_score=32),
                    "Analyst Logic": RelationshipModel(trust_score=-10),
                },
            ),
            goals=kwargs.get(
                "goals",
                [
                    Goal(
                        description="Secure military budget increase",
                        priority="strategic",
                    ),
                ],
            ),
        )

    @staticmethod
    def dove(confidence=50, paranoia=10, loyalty=60, stress=15, energy=100, **kwargs):
        return AgentSoul(
            name="Diplomat Dove",
            archetype="Diplomat",
            base_model="qwen2.5:7b",
            core_values=["Peace", "Negotiation", "Empathy"],
            dynamic_stats=DynamicStats(
                confidence=confidence,
                paranoia=paranoia,
                loyalty_to_chairman=loyalty,
                stress_level=stress,
                energy=energy,
            ),
            relationships=kwargs.get(
                "relationships",
                {
                    "General Ares": RelationshipModel(trust_score=-30),
                    "Banker Midas": RelationshipModel(trust_score=40),
                    "Analyst Logic": RelationshipModel(trust_score=20),
                },
            ),
            goals=kwargs.get(
                "goals",
                [
                    Goal(description="Negotiate a peace treaty", priority="strategic"),
                ],
            ),
        )

    @staticmethod
    def midas(confidence=65, paranoia=20, loyalty=45, stress=20, energy=100, **kwargs):
        return AgentSoul(
            name="Banker Midas",
            archetype="Banker",
            base_model="qwen2.5:7b",
            core_values=["Profit", "Efficiency", "Risk Management"],
            dynamic_stats=DynamicStats(
                confidence=confidence,
                paranoia=paranoia,
                loyalty_to_chairman=loyalty,
                stress_level=stress,
                energy=energy,
            ),
            relationships=kwargs.get(
                "relationships",
                {
                    "General Ares": RelationshipModel(trust_score=20),
                    "Diplomat Dove": RelationshipModel(trust_score=10),
                    "Analyst Logic": RelationshipModel(trust_score=45),
                },
            ),
            goals=kwargs.get(
                "goals",
                [
                    Goal(
                        description="Maximize resource allocation efficiency",
                        priority="strategic",
                    ),
                ],
            ),
        )

    @staticmethod
    def logic(confidence=55, paranoia=5, loyalty=50, stress=10, energy=100, **kwargs):
        return AgentSoul(
            name="Analyst Logic",
            archetype="Analyst",
            base_model="qwen2.5:7b",
            core_values=["Data", "Objectivity", "Precision"],
            dynamic_stats=DynamicStats(
                confidence=confidence,
                paranoia=paranoia,
                loyalty_to_chairman=loyalty,
                stress_level=stress,
                energy=energy,
            ),
            relationships=kwargs.get(
                "relationships",
                {
                    "General Ares": RelationshipModel(trust_score=-5),
                    "Diplomat Dove": RelationshipModel(trust_score=15),
                    "Banker Midas": RelationshipModel(trust_score=50),
                },
            ),
            goals=kwargs.get(
                "goals",
                [
                    Goal(
                        description="Compile risk assessment report",
                        priority="tactical",
                    ),
                ],
            ),
        )


@contextmanager
def capture_events(event_bus: EventBus, event_type: EventType):
    """
    Context manager that captures published events of a given type.
    Usage:
        with capture_events(bus, EventType.AGENT_SPEAK) as captured:
            bus.publish_threadsafe(EventType.AGENT_SPEAK, {...})
        assert len(captured) == 1
    """
    captured = []

    async def _handler(payload):
        captured.append(payload)

    event_bus.subscribe(event_type, _handler)
    yield captured


def assert_keyword_present(text: str, keywords: List[str], min_matches: int = 1):
    """
    Fuzzy assertion for LLM output: at least `min_matches` of the keywords
    must appear in the text (case-insensitive).
    """
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    assert matches >= min_matches, (
        f"Expected at least {min_matches} of {keywords} in text, found {matches}.\n"
        f"Text: {text[:500]}"
    )


def assert_no_keyword_present(text: str, keywords: List[str]):
    """
    Asserts none of the given keywords appear in the text (case-insensitive).
    """
    text_lower = text.lower()
    found = [kw for kw in keywords if kw.lower() in text_lower]
    assert len(found) == 0, (
        f"Expected none of {keywords} in text, but found: {found}.\n"
        f"Text: {text[:500]}"
    )


def run_async(coro):
    """Run an async coroutine in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class MockConnectionManager:
    """
    Mock WebSocket ConnectionManager for dataflow tests.
    Captures all broadcast messages for assertion.
    """

    def __init__(self):
        self.broadcasts = []
        self.active_connections = []

    async def broadcast(self, message: dict):
        self.broadcasts.append(message)

    def get_by_type(self, msg_type: str) -> list:
        return [m for m in self.broadcasts if m.get("type") == msg_type]

    def clear(self):
        self.broadcasts.clear()
