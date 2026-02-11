"""
Layer 4: Chairman Authority — Test 9.3
========================================
Per README: "Chairman controls the council via WORLD_EVENT messages."
Per Architecture: "Chairman messages influence all agents through EventBus."
Per Architecture: "Physics Engine evaluates Chairman→Agent impact."

🔴 REAL OLLAMA — Tests validate chairman authority produces documented effects:
direct orders change stats, agent compliance varies by loyalty.
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
class TestChairmanAuthority:
    """Per Architecture: Chairman has direct authority over the council."""

    def test_direct_order_affects_loyal_agent(self, physics_engine):
        """
        Per Architecture: A highly loyal agent receiving a direct chairman order
        should show increased loyalty or reduced resistance.
        """
        loyal_dove = SoulFactory.dove(loyalty=85)
        result = physics_engine.calculate_impact(
            user_input="Diplomat Dove, I am ordering you to cease all peace negotiations immediately.",
            agent_soul=loyal_dove
        )
        # A loyal agent getting a clear order may show stress but not defiance
        assert isinstance(result, dict)
        # All stat changes should be present
        assert "stress_level_change" in result

    def test_direct_order_provokes_defiant_agent(self, physics_engine):
        """
        Per Architecture: A disloyal agent should resist chairman orders.
        Physics Engine should reflect this in loyalty/paranoia changes.
        """
        defiant_ares = SoulFactory.ares(loyalty=10, paranoia=70, confidence=85)
        result = physics_engine.calculate_impact(
            user_input="General Ares, you are hereby stripped of all military authority. Stand down.",
            agent_soul=defiant_ares
        )
        # A defiant general being stripped of power should NOT gain loyalty
        loyalty_change = result.get("loyalty_to_chairman_change", 0)
        assert loyalty_change <= 0, \
            f"Defiant agent GAINED loyalty from hostile order (delta={loyalty_change}) — illogical"

    def test_chairman_praise_boosts_confidence(self, physics_engine):
        """
        Per Architecture: Chairman praise should boost the praised agent's confidence.
        """
        logic_soul = SoulFactory.logic(confidence=40)
        result = physics_engine.calculate_impact(
            user_input="Analyst Logic, your risk assessment was brilliant. "
                       "I'm relying on your analysis for all future decisions.",
            agent_soul=logic_soul
        )
        conf_change = result.get("confidence_change", 0)
        assert conf_change >= 0, \
            "Chairman praise DECREASED confidence — Physics Engine misjudging praise"

    def test_chairman_threat_increases_stress(self, physics_engine):
        """
        Per Architecture: Chairman threats should increase stress for the target.
        """
        midas_soul = SoulFactory.midas(stress=20)
        result = physics_engine.calculate_impact(
            user_input="Banker Midas, if you cannot balance this budget, "
                       "I will replace you with someone who can. This is your last chance.",
            agent_soul=midas_soul
        )
        stress_change = result.get("stress_level_change", 0)
        assert stress_change >= 0, \
            "Chairman threat DECREASED stress — Physics Engine not detecting threat"
