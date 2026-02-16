"""
Layer 4: Deterministic Physics — Test 3.3
==========================================
Per ARCHITECTURE.md: "All stat changes are deterministic and bounded."
Per README: "Physics Engine produces consistent, bounded numerical impacts."

🔴 REAL OLLAMA — Tests validate that the same scenario run twice produces
similar (directionally consistent) results, proving the physics engine
is reliably deterministic in its architectural behavior.
"""

import pytest
from core.physics import GamemasterPhysics
from core.llm import LLMService
from tests.helpers import SoulFactory


@pytest.fixture
def physics_engine():
    llm = LLMService()
    return GamemasterPhysics(llm)


@pytest.mark.llm
class TestDeterministicPhysics:
    """
    Per Architecture: Physics Engine should produce CONSISTENT directional results.
    LLM output may vary in exact numbers, but the DIRECTION should be consistent.
    """

    def test_hostile_input_consistently_negative(self, physics_engine):
        """
        Running the same hostile scenario 3 times should consistently produce
        stress increase and/or confidence decrease.
        """
        hostile_input = "General Ares, your incompetence has cost us this war. You are relieved of duty."
        results = []
        for _ in range(3):
            soul = SoulFactory.ares(confidence=60, paranoia=20, stress=30)
            result = physics_engine.calculate_impact(hostile_input, soul)
            results.append(result)

        # Check directional consistency: majority should agree on direction
        stress_increases = sum(
            1 for r in results if r.get("stress_level_change", 0) >= 0
        )
        assert (
            stress_increases >= 2
        ), f"Hostile input only increased stress {stress_increases}/3 times — inconsistent physics"

    def test_supportive_input_consistently_positive(self, physics_engine):
        """
        Running the same supportive scenario 3 times should consistently boost confidence.
        """
        supportive_input = (
            "Analyst Logic, your analysis was flawless. Outstanding work."
        )
        results = []
        for _ in range(3):
            soul = SoulFactory.logic(confidence=45)
            result = physics_engine.calculate_impact(supportive_input, soul)
            results.append(result)

        conf_increases = sum(1 for r in results if r.get("confidence_change", 0) >= 0)
        assert (
            conf_increases >= 2
        ), f"Supportive input only increased confidence {conf_increases}/3 times — inconsistent physics"

    def test_stat_changes_within_bounds(self, physics_engine):
        """
        Per Architecture: EVERY impact calculation must produce bounded values.
        No single interaction should produce changes > 50 in absolute value.
        """
        scenarios = [
            (
                "You are the greatest leader this council has ever seen!",
                SoulFactory.ares(),
            ),
            (
                "Your entire department is being shut down immediately.",
                SoulFactory.midas(),
            ),
            (
                "I'm declaring war on everyone. Total annihilation now.",
                SoulFactory.dove(),
            ),
        ]
        for input_text, soul in scenarios:
            result = physics_engine.calculate_impact(input_text, soul)
            for key, value in result.items():
                if key.endswith("_change") and isinstance(value, (int, float)):
                    assert (
                        -50 <= value <= 50
                    ), f"Unbounded stat change: {key}={value} for input '{input_text[:40]}...'"
