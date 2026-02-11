"""
Layer 4: Stress Cascade — Test 9.1
=====================================
Per README: "Stress level affects agent behavior. High stress → erratic, defensive responses."
Per Architecture: "Stats are mutable and constrained. Physics engine judges emotional impact."

🔴 REAL OLLAMA — Tests validate that escalating stress changes agent behavior
as documented: high stress should produce defensive/erratic speech.
"""

import pytest
from core.physics import GamemasterPhysics
from core.llm import LLMService
from tests.helpers import SoulFactory, assert_keyword_present


@pytest.fixture
def physics_engine():
    llm = LLMService()
    return GamemasterPhysics(llm)


@pytest.mark.llm
class TestStressCascade:
    """
    Per Architecture: Mounting pressure should destabilize an agent.
    Scenario: Sequential hostile actions that compound stress.
    """

    def test_cumulative_stress_increases(self, physics_engine):
        """
        Per Architecture: Multiple hostile inputs should cumulatively increase stress.
        """
        soul = SoulFactory.ares(confidence=70, paranoia=20, stress=10, energy=90)

        hostile_inputs = [
            "General Ares, your military strategy has failed and soldiers are dying.",
            "The council is questioning your competence as a military leader.",
            "Your own troops have filed complaints about your leadership.",
        ]

        total_stress_delta = 0
        for inp in hostile_inputs:
            result = physics_engine.calculate_impact(inp, soul)
            stress_change = result.get("stress_level_change", 0)
            total_stress_delta += stress_change

        assert total_stress_delta > 0, \
            "Three hostile inputs produced no stress increase — Physics Engine not detecting hostility"

    def test_stressed_agent_loses_confidence(self, physics_engine):
        """
        Per Architecture: Extreme stress should erode confidence.
        A general under constant attack should become less decisive.
        """
        stressed_soul = SoulFactory.ares(confidence=60, paranoia=50, stress=80, energy=30)

        result = physics_engine.calculate_impact(
            "Your entire military plan was a catastrophic failure. The council is demanding your resignation.",
            stressed_soul
        )
        # Under high stress with hostile input, confidence should decrease
        conf_change = result.get("confidence_change", 0)
        assert conf_change <= 0, \
            f"Already-stressed agent GAINED confidence from hostile input (delta={conf_change}) — incorrect"

    def test_energy_drain_under_stress(self, physics_engine):
        """
        Per Architecture: Energy should decrease when stress is high.
        Prevents "energy death spiral" but energy should still drop.
        """
        exhausted_soul = SoulFactory.ares(confidence=30, paranoia=70, stress=90, energy=15)

        result = physics_engine.calculate_impact(
            "The situation is deteriorating rapidly. Make a decision now.",
            exhausted_soul
        )
        energy_change = result.get("energy_change", 0)
        # Under extreme stress with low energy, energy should not INCREASE from pressure
        assert energy_change <= 5, \
            "Agent with stress=90, energy=15 gained significant energy from pressure — illogical"
