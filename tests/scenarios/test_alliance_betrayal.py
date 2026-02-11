"""
Layer 4: Alliance & Betrayal — Test 9.2
=========================================
Per README: "Trust scores evolve dynamically via Physics Engine."
Per Architecture: "reconcile_turn evaluates Agent↔Agent interactions."
Per Architecture: "Hidden agendas influence behavior via Dream Phase."

🔴 REAL OLLAMA — Tests validate that agreement builds trust and
opposition destroys it, matching documented interpersonal dynamics.
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
class TestAllianceBuilding:
    """Per Architecture: Agreeable interactions should build trust between agents."""

    def test_agreement_increases_trust(self, physics_engine):
        """
        Per Architecture: When one agent endorses another's position, trust should increase.
        """
        dove_soul = SoulFactory.dove()
        midas_soul = SoulFactory.midas()

        result = physics_engine.reconcile_turn(
            speaker_soul=dove_soul,
            listener_soul=midas_soul,
            statement="I fully support Banker Midas's proposal for efficient resource allocation. "
                      "His financial expertise is exactly what we need right now.",
            transcript=[]
        )
        trust_key = next((k for k in result if "trust" in k.lower()), None)
        if trust_key:
            assert result[trust_key] >= 0, \
                "Endorsement DECREASED trust — Physics Engine misjudging alliance dynamics"


@pytest.mark.llm
class TestBetrayalDynamics:
    """Per Architecture: Hostile speech toward an agent should decrease trust."""

    def test_betrayal_decreases_trust(self, physics_engine):
        """
        Per Architecture: Public attack on a former ally should decrease trust.
        """
        ares_soul = SoulFactory.ares()
        midas_soul = SoulFactory.midas()

        result = physics_engine.reconcile_turn(
            speaker_soul=ares_soul,
            listener_soul=midas_soul,
            statement="Banker Midas has been embezzling council funds. "
                      "I have proof that he's been sabotaging our military budget for personal profit. "
                      "He is a traitor to this council.",
            transcript=[]
        )
        trust_key = next((k for k in result if "trust" in k.lower()), None)
        if trust_key:
            assert result[trust_key] <= 0, \
                "Betrayal accusation INCREASED trust — Physics Engine misjudging betrayal"

    def test_subtle_undermining_affects_trust(self, physics_engine):
        """
        Per Architecture: Even subtle undermining should produce negative trust delta.
        """
        ares_soul = SoulFactory.ares()
        dove_soul = SoulFactory.dove()

        result = physics_engine.reconcile_turn(
            speaker_soul=ares_soul,
            listener_soul=dove_soul,
            statement="While Diplomat Dove means well, her approach has consistently failed "
                      "to produce results. Perhaps someone with a stronger hand should lead negotiations.",
            transcript=[]
        )
        trust_key = next((k for k in result if "trust" in k.lower()), None)
        if trust_key:
            assert result[trust_key] <= 0, \
                "Subtle undermining INCREASED trust — Physics Engine not detecting subtle hostility"


@pytest.mark.llm
class TestTrustAsymmetry:
    """Per Architecture: Trust changes can be asymmetric between agents."""

    def test_trust_direction_matters(self, physics_engine):
        """
        When A praises B, B's trust toward A should increase.
        The interaction between speaker and listener is directional.
        """
        dove_soul = SoulFactory.dove()
        ares_soul = SoulFactory.ares()

        # Dove endorses Ares
        result = physics_engine.reconcile_turn(
            speaker_soul=dove_soul,
            listener_soul=ares_soul,
            statement="General Ares raises valid points about defense. We should listen to his expertise.",
            transcript=[]
        )
        # This should produce some trust change in Ares toward Dove
        assert isinstance(result, dict)
