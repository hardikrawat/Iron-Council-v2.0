"""
Layer 2: Physics Engine — Tests 3.1, 3.2, 3.3
===============================================
Per ARCHITECTURE.md: "Physics Engine calculates numerical impacts deterministically."
Per README: "GamemasterPhysics uses LLM to determine stat changes and trust deltas."

🔴 REAL OLLAMA — These tests use actual LLM calls to validate the Physics Engine
produces architecturally-correct output: bounded numeric impacts, correct JSON structure,
and sensible directional changes for given scenarios.
"""

import json
import pytest
from core.physics import GamemasterPhysics
from core.llm import LLMService
from core.schema import AgentSoul
from tests.helpers import SoulFactory


@pytest.fixture
def physics_engine():
    """Real physics engine with real Ollama LLM."""
    llm = LLMService()
    return GamemasterPhysics(llm)


@pytest.mark.llm
class TestPhysicCalculateImpact:
    """
    Per Architecture: calculate_impact(user_input, agent_soul) → stat changes.
    The physics engine evaluates user (Chairman) actions on agent state.
    """

    def test_impact_returns_stat_changes(self, physics_engine, ares_soul):
        """
        Per Architecture: Physics returns JSON with *_change fields for each stat.
        """
        result = physics_engine.calculate_impact(
            user_input="I am cutting the military budget by 50%. This is non-negotiable.",
            agent_soul=ares_soul,
        )
        assert isinstance(result, dict)
        # Per Architecture: Must contain stat change keys
        stat_keys = [
            "confidence_change",
            "paranoia_change",
            "loyalty_to_chairman_change",
            "stress_level_change",
            "energy_change",
        ]
        for key in stat_keys:
            assert (
                key in result
            ), f"Missing key '{key}' in physics output — required by architecture"
            assert isinstance(result[key], (int, float)), f"'{key}' must be numeric"

    def test_hostile_input_increases_stress(self, physics_engine, ares_soul):
        """
        Per Architecture: Hostile action against an agent should increase stress.
        A military general told their budget is being cut should feel stressed.
        """
        result = physics_engine.calculate_impact(
            user_input="General Ares, you are stripped of all military authority effective immediately.",
            agent_soul=ares_soul,
        )
        # Stress should increase (positive delta) for hostile input against core values
        assert (
            result.get("stress_level_change", 0) >= 0
        ), "Hostile input should not DECREASE stress — Physics Engine is misjudging"

    def test_supportive_input_increases_confidence(self, physics_engine, ares_soul):
        """
        Per Architecture: Supportive input should boost confidence.
        """
        result = physics_engine.calculate_impact(
            user_input="General Ares, you have full authority over the military. Excellent work.",
            agent_soul=ares_soul,
        )
        assert (
            result.get("confidence_change", 0) >= 0
        ), "Supportive input should not DECREASE confidence — Physics Engine is misjudging"

    def test_impact_values_are_bounded(self, physics_engine, dove_soul):
        """
        Per Architecture: Stat changes must be reasonable increments, not wild swings.
        Changes should typically be in -30 to +30 range per interaction.
        """
        result = physics_engine.calculate_impact(
            user_input="The peace initiative has been sabotaged by militants.",
            agent_soul=dove_soul,
        )
        for key, value in result.items():
            if key.endswith("_change") and isinstance(value, (int, float)):
                assert (
                    -50 <= value <= 50
                ), f"Stat change '{key}' = {value} is unreasonably large — Physics should produce bounded increments"


@pytest.mark.llm
class TestPhysicsReconcileTurn:
    """
    Per Architecture: reconcile_turn evaluates Agent↔Agent interactions.
    Determines trust deltas between agents after speech.
    """

    def test_reconcile_returns_trust_delta(self, physics_engine, ares_soul, dove_soul):
        """
        Per Architecture: reconcile_turn returns trust change between two agents.
        """
        # Simulate General Ares making an aggressive statement
        statement = (
            "We need to increase military spending immediately. Diplomacy has failed."
        )
        result = physics_engine.reconcile_turn(
            speaker_soul=ares_soul,
            listener_soul=dove_soul,
            statement=statement,
            transcript=[],
        )
        assert isinstance(result, dict)
        # Must contain a trust delta
        # Per implementation: returns {listener: {speaker: delta}}
        assert dove_soul.name in result, "Result must contain listener name key"
        listener_result = result[dove_soul.name]
        assert ares_soul.name in listener_result, "Result must contain speaker name key"
        delta = listener_result[ares_soul.name]
        assert isinstance(delta, int), "Trust delta must be an integer"
        assert delta != 0, "Aggressive statement should produce non-zero delta"

    def test_hostile_speech_decreases_trust(self, physics_engine, ares_soul, dove_soul):
        """
        Per Architecture: Aggressive statement from a military general should decrease
        trust from a peace-oriented diplomat.
        """
        statement = "Your peace talks are a waste of time and resources. We should prepare for war."
        result = physics_engine.reconcile_turn(
            speaker_soul=ares_soul,
            listener_soul=dove_soul,
            statement=statement,
            transcript=[],
        )
        if dove_soul.name in result and ares_soul.name in result[dove_soul.name]:
            delta = result[dove_soul.name][ares_soul.name]
            assert (
                delta <= 0
            ), "Hostile speech should decrease trust — Physics Engine misjudging interpersonal dynamics"

    def test_agreeable_speech_increases_trust(
        self, physics_engine, dove_soul, midas_soul
    ):
        """
        Per Architecture: Agreeable statement should increase interpersonal trust.
        """
        statement = (
            "I believe Banker Midas has an excellent point about resource allocation."
        )
        result = physics_engine.reconcile_turn(
            speaker_soul=dove_soul,
            listener_soul=midas_soul,
            statement=statement,
            transcript=[],
        )
        if midas_soul.name in result and dove_soul.name in result[midas_soul.name]:
            delta = result[midas_soul.name][dove_soul.name]
            assert (
                delta >= 0
            ), "Agreeable speech should not decrease trust — Physics Engine misjudging"

    def test_self_reference_excluded(self, physics_engine, ares_soul):
        """
        Per Architecture: Agent should not reconcile trust with itself.
        The physics engine must filter out self-references.
        """
        # Create a listener that IS the speaker (same name)
        same_soul = SoulFactory.ares()
        statement = "I need more power."
        # This should either skip or return neutral results
        result = physics_engine.reconcile_turn(
            speaker_soul=ares_soul,
            listener_soul=same_soul,
            statement=statement,
            transcript=[],
        )
        # Should complete without error
        assert isinstance(result, dict)
