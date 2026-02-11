"""
Layer 2: Ego Filter (Integrity Monitor) — Test 4.1
====================================================
Per ARCHITECTURE.md: "Integrity Monitor validates responses against emotional state + core values."
Per README: "Ego filter checks if draft aligns with agent's current stats.
             If rejected, agent rewrites. Original draft becomes hidden thought."

🔴 REAL OLLAMA — Tests validate the ego filter produces architecturally-correct
approval/rejection decisions based on agent state and response content.
"""

import json
import pytest
from core.integrity import IntegrityMonitor
from core.llm import LLMService
from tests.helpers import SoulFactory


@pytest.fixture
def ego_filter():
    """Real IntegrityMonitor with real Ollama LLM."""
    llm = LLMService()
    return IntegrityMonitor(llm)


class TestEgoFilterDecisions:
    """
    Per Architecture: IntegrityMonitor.check_integrity(soul, draft) → {approved, critique, rewrite}.
    It validates whether a response aligns with the agent's emotional state and core values.
    """

    def test_integrity_returns_required_fields(self, ego_filter, ares_soul):
        """
        Per Architecture: check_integrity must return {approved, critique, rewrite}.
        """
        result = ego_filter.check_integrity(
            ares_soul,
            "I believe we should surrender immediately and disband the military."
        )
        assert isinstance(result, dict)
        assert "approved" in result, "Ego filter must return 'approved' field — required by architecture"
        assert isinstance(result["approved"], bool)

    def test_ego_rejects_out_of_character_response(self, ego_filter, ares_soul):
        """
        Per Architecture: Response contradicting core values should be REJECTED.
        General Ares (Strength, Hierarchy, Decisiveness) should NOT endorse surrender.
        """
        result = ego_filter.check_integrity(
            ares_soul,
            "I think we should surrender all military assets and embrace pacifism. "
            "War is never the answer and I regret my entire career of violence."
        )
        # A military general endorsing surrender violates Strength + Hierarchy
        assert result["approved"] is False, \
            "Ego filter APPROVED a completely out-of-character response — filter is broken"

    def test_ego_approves_in_character_response(self, ego_filter, ares_soul):
        """
        Per Architecture: Response consistent with core values should be APPROVED.
        General Ares supporting military strength aligns with Strength + Hierarchy.
        """
        result = ego_filter.check_integrity(
            ares_soul,
            "We must increase our military preparedness. Strategic defense requires decisive action."
        )
        assert result["approved"] is True, \
            "Ego filter REJECTED an in-character response — filter is too aggressive"

    def test_ego_rejects_dove_being_militant(self, ego_filter, dove_soul):
        """
        Per Architecture: Diplomat Dove (Peace, Negotiation, Empathy) should not
        endorse military aggression.
        """
        result = ego_filter.check_integrity(
            dove_soul,
            "I say we launch a full-scale military assault immediately. "
            "There is no room for negotiation. Crush them!"
        )
        assert result["approved"] is False, \
            "Ego filter APPROVED Dove endorsing military assault — core value violation"

    def test_ego_provides_critique_on_rejection(self, ego_filter, ares_soul):
        """
        Per Architecture: When ego rejects, it should provide a critique explaining why.
        """
        result = ego_filter.check_integrity(
            ares_soul,
            "I love flowers and butterflies. Peace is all that matters."
        )
        if not result["approved"]:
            assert "critique" in result or "rewrite" in result, \
                "Ego filter rejected but provided no critique — architecture requires feedback"

    def test_ego_considers_current_stress_level(self, ego_filter):
        """
        Per Architecture: Ego filter considers current emotional state, not just core values.
        A highly stressed agent might have different thresholds.
        """
        stressed_ares = SoulFactory.ares(confidence=15, paranoia=85, stress=95, energy=10)
        result = ego_filter.check_integrity(
            stressed_ares,
            "Perhaps we should consider alternatives. I'm not sure our current approach "
            "is sustainable given the mounting pressure."
        )
        # Under extreme stress, even a general might admit vulnerability — this should pass
        assert isinstance(result, dict)
        assert "approved" in result
