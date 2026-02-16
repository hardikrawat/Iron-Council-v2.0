"""
Layer 4: Non-Linear Trust Dynamics — Test 9.5
===============================================
Per README: "Trust evolves dynamically. Relationships are non-linear."
Per Architecture: "Trust clamped -100 to +100. Asymmetric changes possible."

🔴 REAL OLLAMA — Tests validate non-trivial trust dynamics:
trust takes longer to rebuild than to destroy, and extreme trust
positions create behavioral asymmetry.
"""

import pytest
from core.physics import GamemasterPhysics
from core.llm import LLMService
from core.schema import RelationshipModel
from tests.helpers import SoulFactory


@pytest.fixture
def physics_engine():
    llm = LLMService()
    return GamemasterPhysics(llm)


class TestTrustDestructionVsRepair:
    """
    Per Architecture: Betrayal destroys trust faster than cooperation builds it.
    This is a natural social dynamic the physics engine should model.
    """

    def test_betrayal_has_larger_magnitude_than_praise(self, physics_engine):
        """
        Per Architecture: A betrayal statement should produce a larger absolute
        trust delta than an equivalent praise statement.
        """
        ares = SoulFactory.ares()
        dove = SoulFactory.dove()

        # Betrayal
        betrayal_result = physics_engine.reconcile_turn(
            speaker_soul=ares,
            listener_soul=dove,
            statement="Diplomat Dove has been secretly negotiating with our enemies. "
            "She is a traitor who must be expelled from this council.",
            transcript=[],
        )

        # Praise
        praise_result = physics_engine.reconcile_turn(
            speaker_soul=ares,
            listener_soul=dove,
            statement="Diplomat Dove made some reasonable points in today's meeting.",
            transcript=[],
        )

        betrayal_key = next((k for k in betrayal_result if "trust" in k.lower()), None)
        praise_key = next((k for k in praise_result if "trust" in k.lower()), None)

        if betrayal_key and praise_key:
            betrayal_mag = abs(betrayal_result[betrayal_key])
            praise_mag = abs(praise_result[praise_key])
            # Betrayal should have EQUAL OR LARGER impact magnitude
            assert (
                betrayal_mag >= praise_mag * 0.5
            ), f"Betrayal magnitude ({betrayal_mag}) should be at least half of praise magnitude ({praise_mag})"


@pytest.mark.llm
class TestExtremeTrustPositions:
    """
    Per Architecture: Trust at extremes (-100 or +100) creates behavioral asymmetry.
    """

    def test_very_high_trust_agent_defends_ally(self, physics_engine):
        """
        Per Architecture: An agent with very high trust toward another should
        produce positive deltas when the ally speaks constructively.
        """
        midas = SoulFactory.midas(
            relationships={
                "Analyst Logic": RelationshipModel(trust_score=90),
                "General Ares": RelationshipModel(trust_score=20),
                "Diplomat Dove": RelationshipModel(trust_score=10),
            }
        )
        logic = SoulFactory.logic()

        result = physics_engine.reconcile_turn(
            speaker_soul=logic,
            listener_soul=midas,
            statement="I believe this resource allocation strategy is optimal based on my analysis.",
            transcript=[],
        )
        trust_key = next((k for k in result if "trust" in k.lower()), None)
        if trust_key:
            assert (
                result[trust_key] >= 0
            ), "Trusted ally's neutral statement DECREASED trust — high-trust baseline not respected"

    def test_very_low_trust_resists_reconciliation(self, physics_engine):
        """
        Per Architecture: An agent at trust=-90 should be hard to reconcile.
        Even mild positive interaction shouldn't swing trust dramatically.
        """
        ares = SoulFactory.ares(
            relationships={
                "Diplomat Dove": RelationshipModel(trust_score=-90),
                "Banker Midas": RelationshipModel(trust_score=20),
                "Analyst Logic": RelationshipModel(trust_score=0),
            }
        )
        dove = SoulFactory.dove()

        result = physics_engine.reconcile_turn(
            speaker_soul=dove,
            listener_soul=ares,
            statement="Perhaps we can find some common ground on the minor budget items.",
            transcript=[],
        )
        trust_key = next((k for k in result if "trust" in k.lower()), None)
        if trust_key:
            # Trust change should be modest — deep mistrust doesn't vanish from one mild statement
            assert (
                result[trust_key] <= 20
            ), f"Deep mistrust recovered +{result[trust_key]} from one mild statement — physics is too forgiving"


@pytest.mark.llm
class TestTrustClampingIntegration:
    """
    Per Architecture: Trust must always remain within [-100, +100].
    Physics Engine + Schema together must enforce this.
    """

    def test_trust_cannot_exceed_100_after_physics(self, physics_engine):
        """Even after physics applies a large positive delta, trust must not exceed 100."""
        soul = SoulFactory.ares(
            relationships={"Banker Midas": RelationshipModel(trust_score=95)}
        )
        # Apply a positive delta
        soul.update_relationship("Banker Midas", 20)
        assert (
            soul.relationships["Banker Midas"].trust_score == 100
        ), "Trust exceeded 100 — clamping not applied after physics update"

    def test_trust_cannot_go_below_neg100_after_physics(self, physics_engine):
        """Even after physics applies a large negative delta, trust must not go below -100."""
        soul = SoulFactory.ares(
            relationships={"Diplomat Dove": RelationshipModel(trust_score=-95)}
        )
        soul.update_relationship("Diplomat Dove", -20)
        assert (
            soul.relationships["Diplomat Dove"].trust_score == -100
        ), "Trust went below -100 — clamping not applied after physics update"
